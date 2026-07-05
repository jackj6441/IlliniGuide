"""Embedding backends for RAG.

Two implementations:
- ``MockEmbeddingClient``: deterministic bag-of-words hash embedding used in
  unit tests and any environment where the sentence-transformers wheel is not
  installed. Similar texts share dimensions so cosine similarity is meaningful
  for wiring tests, but the vectors are *not* semantically meaningful — do not
  ship this to production retrieval.
- ``SentenceTransformerBackend``: wraps ``sentence-transformers/all-MiniLM-L6-v2``
  (384 dim) with lazy model loading so importing this module is cheap even when
  torch is unavailable.

Both satisfy the ``EmbeddingClient`` Protocol so the retriever and ingestion
pipeline can stay backend-agnostic.
"""

from __future__ import annotations

import hashlib
import math
import os
import struct
import threading
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

BACKEND_MOCK = "mock"
BACKEND_SENTENCE_TRANSFORMER = "sentence_transformer"

KNOWN_BACKENDS = frozenset({BACKEND_MOCK, BACKEND_SENTENCE_TRANSFORMER})

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_MOCK_DIMENSION = 384
MINILM_L6_V2_DIMENSION = 384


@runtime_checkable
class EmbeddingClient(Protocol):
    """Unified embedding interface every backend must satisfy.

    All backends expose ``backend_name`` / ``model_name`` / ``dimension`` and a
    synchronous batch ``embed`` call. Callers running inside async code should
    wrap ``embed`` in ``asyncio.to_thread`` since the underlying work is
    CPU-bound.
    """

    backend_name: str
    model_name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        ...


def _unit_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _tokenize(text: str) -> list[str]:
    return [tok for tok in text.lower().split() if tok]


def _hash_token_to_vector(token: str, dimension: int) -> list[float]:
    """Map a token to a deterministic float vector via SHA256.

    We derive 4-byte little-endian floats from the hash digest, repeating the
    digest across as many bytes as we need. Values are recentered to [-0.5, 0.5]
    so summing many tokens produces a near-zero-mean vector suited to cosine
    similarity.
    """
    needed_bytes = dimension * 4
    buf = b""
    counter = 0
    while len(buf) < needed_bytes:
        buf += hashlib.sha256(f"{token}:{counter}".encode("utf-8")).digest()
        counter += 1
    values: list[float] = []
    for i in range(dimension):
        (raw,) = struct.unpack_from("<I", buf, i * 4)
        values.append(raw / 0xFFFFFFFF - 0.5)
    return values


@dataclass
class MockEmbeddingClient:
    """Deterministic bag-of-words hash embedding for tests and local dev."""

    model_name: str = "mock-embedding"
    dimension: int = DEFAULT_MOCK_DIMENSION
    backend_name: str = BACKEND_MOCK
    _token_cache: dict[str, list[float]] = field(default_factory=dict, repr=False)

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            tokens = _tokenize(text)
            if not tokens:
                results.append([0.0] * self.dimension)
                continue
            summed = [0.0] * self.dimension
            for tok in tokens:
                vec = self._token_cache.get(tok)
                if vec is None:
                    vec = _hash_token_to_vector(tok, self.dimension)
                    self._token_cache[tok] = vec
                for i, x in enumerate(vec):
                    summed[i] += x
            results.append(_unit_normalize(summed))
        return results


class SentenceTransformerBackend:
    """Lazy wrapper around a HuggingFace sentence-transformers model.

    The heavy ``SentenceTransformer`` import happens on first ``embed`` call so
    importing this module (or the factory) never forces torch to load.
    """

    backend_name: str = BACKEND_SENTENCE_TRANSFORMER

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        dimension: int = MINILM_L6_V2_DIMENSION,
        device: str | None = None,
        batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._device = device
        self._batch_size = batch_size
        self._model = None  # type: ignore[assignment]

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "sentence-transformers is not installed. Install with "
                "`pip install sentence-transformers` to use "
                "SentenceTransformerBackend."
            ) from exc
        self._model = SentenceTransformer(self.model_name, device=self._device)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        assert self._model is not None
        arr = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [list(map(float, row)) for row in arr]


def get_embedding_client(
    backend: str | None = None,
    *,
    model_name: str | None = None,
) -> EmbeddingClient:
    """Factory reading ``EMBEDDING_BACKEND`` / ``EMBEDDING_MODEL_NAME`` env vars.

    Defaults to the mock backend so imports and tests never depend on torch.
    """
    resolved = (backend or os.getenv("EMBEDDING_BACKEND", BACKEND_MOCK)).strip().lower()
    if resolved not in KNOWN_BACKENDS:
        raise ValueError(
            f"Unknown embedding backend '{resolved}'. "
            f"Expected one of: {sorted(KNOWN_BACKENDS)}"
        )
    if resolved == BACKEND_MOCK:
        return MockEmbeddingClient(
            model_name=model_name or os.getenv("EMBEDDING_MODEL_NAME", "mock-embedding")
        )
    return SentenceTransformerBackend(
        model_name=model_name
        or os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_MODEL_NAME)
    )


_default_client_lock = threading.Lock()
_default_client: EmbeddingClient | None = None


def get_default_embedding_client() -> EmbeddingClient:
    """Return the process-wide embedding client, constructing it on first use.

    Callers in the tools layer share one instance so the sentence-transformers
    model is loaded at most once per process. Tests override behaviour with
    ``set_default_embedding_client`` or ``reset_default_embedding_client``.
    """
    global _default_client
    if _default_client is None:
        with _default_client_lock:
            if _default_client is None:
                _default_client = get_embedding_client()
    return _default_client


def set_default_embedding_client(client: EmbeddingClient | None) -> None:
    """Test helper: install a specific client (or None to force re-init)."""
    global _default_client
    with _default_client_lock:
        _default_client = client


def reset_default_embedding_client() -> None:
    """Test helper: drop the cached singleton so env changes re-take effect."""
    set_default_embedding_client(None)


__all__ = [
    "BACKEND_MOCK",
    "BACKEND_SENTENCE_TRANSFORMER",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MOCK_DIMENSION",
    "MINILM_L6_V2_DIMENSION",
    "EmbeddingClient",
    "MockEmbeddingClient",
    "SentenceTransformerBackend",
    "get_embedding_client",
    "get_default_embedding_client",
    "set_default_embedding_client",
    "reset_default_embedding_client",
]
