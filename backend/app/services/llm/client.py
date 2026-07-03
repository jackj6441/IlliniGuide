import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, runtime_checkable

from app.services.llm.schemas import LLMMessage, LLMResponse


BACKEND_MOCK = "mock"
BACKEND_VLLM_REMOTE = "vllm_remote"
BACKEND_EXTERNAL_DEBUG = "external_debug"

KNOWN_BACKENDS = frozenset({BACKEND_MOCK, BACKEND_VLLM_REMOTE, BACKEND_EXTERNAL_DEBUG})

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 512
DEFAULT_MOCK_MODEL_NAME = "mock-model"


@runtime_checkable
class LLMClient(Protocol):
    """Unified LLM interface every backend must satisfy.

    Concrete backends must expose ``backend_name`` / ``model_name`` attributes
    and an async ``generate`` method returning an ``LLMResponse``.
    """

    backend_name: str
    model_name: str

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> LLMResponse:  # pragma: no cover - protocol
        ...

    def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[str]:  # pragma: no cover - protocol
        ...


MOCK_STREAM_CHUNK_SIZE = 6
MOCK_STREAM_DELAY_SECONDS = 0.005


@dataclass
class MockLLMClient:
    """Deterministic in-process backend used for tests and local development.

    Every call echoes the last user message with a fixed prefix so tests can
    assert exact content, while the shape (latency_ms, token counts, backend
    name) matches what a real backend will fill in.
    """

    model_name: str = DEFAULT_MOCK_MODEL_NAME
    backend_name: str = BACKEND_MOCK

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> LLMResponse:
        _validate_generate_kwargs(temperature, max_tokens)

        start = perf_counter()
        last_user = _last_user_content(messages)
        content = (
            f"[mock backend={self.backend_name} model={self.model_name}] "
            f"Received {len(messages)} messages. "
            f"Last user turn: {last_user!r}. "
            "TODO: replace with vLLM-generated answer in Task C3."
        )
        latency_ms = max(0, int((perf_counter() - start) * 1000))

        return LLMResponse(
            content=content,
            model=self.model_name,
            backend=self.backend_name,
            latency_ms=latency_ms,
            prompt_tokens=_estimate_tokens(
                " ".join(msg.content for msg in messages)
            ),
            completion_tokens=_estimate_tokens(content),
        )

    async def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[str]:
        _validate_generate_kwargs(temperature, max_tokens)

        last_user = _last_user_content(messages)
        content = (
            f"[mock stream backend={self.backend_name} model={self.model_name}] "
            f"Echoing last user turn: {last_user!r}. "
            "TODO: replace with vLLM streamed answer in Task C3."
        )
        for start in range(0, len(content), MOCK_STREAM_CHUNK_SIZE):
            await asyncio.sleep(MOCK_STREAM_DELAY_SECONDS)
            yield content[start : start + MOCK_STREAM_CHUNK_SIZE]


def create_llm_client(
    *,
    backend: str | None = None,
    model_name: str | None = None,
) -> LLMClient:
    """Return an ``LLMClient`` for the requested backend.

    Resolution order:

    1. Explicit ``backend`` / ``model_name`` arguments if provided.
    2. ``LLM_BACKEND`` / ``MODEL_NAME`` env vars.
    3. Defaults (``mock`` / ``mock-model``).

    Unknown backends raise ``ValueError``. Backends whose implementation is
    not landed yet raise ``NotImplementedError`` — callers can rely on the
    factory contract even before C3 lands the real vLLM client.
    """
    resolved_backend = (backend or os.getenv("LLM_BACKEND", BACKEND_MOCK)).strip().lower()

    if resolved_backend == BACKEND_MOCK:
        return MockLLMClient(
            model_name=model_name or os.getenv("MODEL_NAME", DEFAULT_MOCK_MODEL_NAME)
        )
    if resolved_backend == BACKEND_VLLM_REMOTE:
        return _build_vllm_remote_client(model_name)
    if resolved_backend == BACKEND_EXTERNAL_DEBUG:
        return _build_external_debug_client(model_name)
    raise ValueError(
        f"Unknown LLM_BACKEND value: {resolved_backend!r}. "
        f"Expected one of: {sorted(KNOWN_BACKENDS)}."
    )


def _build_vllm_remote_client(model_name: str | None) -> "LLMClient":
    # local import avoids a hard cycle: vllm_backend imports validators from
    # this module, so we import it lazily only when the factory needs it.
    from app.services.llm.vllm_backend import VLLMRemoteClient

    base_url = os.getenv("VLLM_BASE_URL")
    if not base_url:
        raise ValueError(
            "LLM_BACKEND=vllm_remote requires the VLLM_BASE_URL env var to be set."
        )
    return VLLMRemoteClient(
        base_url=base_url.rstrip("/"),
        model_name=model_name or os.getenv("MODEL_NAME") or "vllm-model",
        api_key=os.getenv("VLLM_API_KEY") or None,
        backend_name=BACKEND_VLLM_REMOTE,
    )


def _build_external_debug_client(model_name: str | None) -> "LLMClient":
    from app.services.llm.vllm_backend import VLLMRemoteClient

    base_url = (
        os.getenv("EXTERNAL_LLM_BASE_URL") or os.getenv("VLLM_BASE_URL")
    )
    if not base_url:
        raise ValueError(
            "LLM_BACKEND=external_debug requires EXTERNAL_LLM_BASE_URL "
            "(or VLLM_BASE_URL as a fallback) to be set."
        )
    return VLLMRemoteClient(
        base_url=base_url.rstrip("/"),
        model_name=model_name or os.getenv("MODEL_NAME") or "external-debug-model",
        api_key=(
            os.getenv("EXTERNAL_LLM_API_KEY") or os.getenv("VLLM_API_KEY") or None
        ),
        backend_name=BACKEND_EXTERNAL_DEBUG,
    )


def _last_user_content(messages: list[LLMMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _estimate_tokens(text: str) -> int:
    """Rough token count used by the mock backend.

    Real backends will return exact counts from the model server. We use a
    simple word count here so downstream metrics do not have to special-case
    ``None`` values coming out of the mock path.
    """
    return max(1, len(text.split()))


def _validate_generate_kwargs(temperature: float, max_tokens: int) -> None:
    if not 0.0 <= temperature <= 2.0:
        raise ValueError(
            f"temperature must be in [0.0, 2.0], got {temperature!r}."
        )
    if max_tokens < 1:
        raise ValueError(f"max_tokens must be >= 1, got {max_tokens!r}.")
