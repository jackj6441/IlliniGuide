"""Unit tests for embedding backends."""

from __future__ import annotations

import math

import pytest

from app.services.rag.embeddings import (
    BACKEND_MOCK,
    BACKEND_SENTENCE_TRANSFORMER,
    DEFAULT_MOCK_DIMENSION,
    EmbeddingClient,
    MockEmbeddingClient,
    SentenceTransformerBackend,
    get_embedding_client,
)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class TestMockEmbeddingClient:
    def test_dimension_defaults_to_384(self) -> None:
        client = MockEmbeddingClient()
        assert client.dimension == DEFAULT_MOCK_DIMENSION
        [vec] = client.embed(["hello world"])
        assert len(vec) == DEFAULT_MOCK_DIMENSION

    def test_custom_dimension_respected(self) -> None:
        client = MockEmbeddingClient(dimension=16)
        [vec] = client.embed(["hi"])
        assert len(vec) == 16

    def test_deterministic_across_calls(self) -> None:
        client = MockEmbeddingClient()
        first = client.embed(["ECE 391 systems programming"])
        second = client.embed(["ECE 391 systems programming"])
        assert first == second

    def test_deterministic_across_instances(self) -> None:
        a = MockEmbeddingClient().embed(["hardware design"])
        b = MockEmbeddingClient().embed(["hardware design"])
        assert a == b

    def test_batch_returns_one_vector_per_input(self) -> None:
        client = MockEmbeddingClient()
        vecs = client.embed(["a", "b", "c"])
        assert len(vecs) == 3
        assert all(len(v) == client.dimension for v in vecs)

    def test_non_empty_vectors_are_unit_normalized(self) -> None:
        client = MockEmbeddingClient()
        [vec] = client.embed(["parallel programming CUDA"])
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_empty_text_returns_zero_vector(self) -> None:
        client = MockEmbeddingClient()
        [vec] = client.embed([""])
        assert vec == [0.0] * client.dimension

    def test_whitespace_only_text_returns_zero_vector(self) -> None:
        client = MockEmbeddingClient()
        [vec] = client.embed(["   \n\t"])
        assert vec == [0.0] * client.dimension

    def test_shared_tokens_produce_positive_similarity(self) -> None:
        client = MockEmbeddingClient()
        a, b = client.embed(
            [
                "GPU programming and CUDA parallelism",
                "CUDA programming for GPU acceleration",
            ]
        )
        c = client.embed(["digital hardware SystemVerilog FPGA"])[0]
        similar = _cosine(a, b)
        different = _cosine(a, c)
        assert similar > different
        assert similar > 0.3

    def test_case_insensitive_tokenization(self) -> None:
        client = MockEmbeddingClient()
        upper = client.embed(["ECE 391 SYSTEMS"])[0]
        lower = client.embed(["ece 391 systems"])[0]
        assert upper == lower

    def test_empty_input_list_returns_empty(self) -> None:
        client = MockEmbeddingClient()
        assert client.embed([]) == []

    def test_backend_and_model_name(self) -> None:
        client = MockEmbeddingClient()
        assert client.backend_name == BACKEND_MOCK
        assert client.model_name == "mock-embedding"

    def test_satisfies_protocol(self) -> None:
        client = MockEmbeddingClient()
        assert isinstance(client, EmbeddingClient)


class TestSentenceTransformerBackend:
    def test_module_load_does_not_require_torch(self) -> None:
        backend = SentenceTransformerBackend()
        assert backend.dimension == 384
        assert backend.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert backend.backend_name == BACKEND_SENTENCE_TRANSFORMER
        assert backend._model is None

    def test_embed_empty_list_short_circuits_without_loading_model(self) -> None:
        backend = SentenceTransformerBackend()
        assert backend.embed([]) == []
        assert backend._model is None


class TestGetEmbeddingClient:
    def test_defaults_to_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
        client = get_embedding_client()
        assert isinstance(client, MockEmbeddingClient)

    def test_explicit_mock_backend(self) -> None:
        client = get_embedding_client(backend="mock")
        assert isinstance(client, MockEmbeddingClient)

    def test_env_var_selects_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDING_BACKEND", "sentence_transformer")
        client = get_embedding_client()
        assert isinstance(client, SentenceTransformerBackend)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown embedding backend"):
            get_embedding_client(backend="not_a_backend")

    def test_model_name_override_reaches_mock(self) -> None:
        client = get_embedding_client(backend="mock", model_name="custom-mock")
        assert client.model_name == "custom-mock"

    def test_env_model_name_reaches_sentence_transformer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_BACKEND", "sentence_transformer")
        monkeypatch.setenv(
            "EMBEDDING_MODEL_NAME", "sentence-transformers/all-mpnet-base-v2"
        )
        client = get_embedding_client()
        assert client.model_name == "sentence-transformers/all-mpnet-base-v2"
