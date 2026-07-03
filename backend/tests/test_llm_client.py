import dataclasses

import pytest

from app.services.llm import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    MockLLMClient,
    create_llm_client,
)
from app.services.llm.client import (
    BACKEND_EXTERNAL_DEBUG,
    BACKEND_MOCK,
    BACKEND_VLLM_REMOTE,
)


@pytest.fixture
def sample_messages() -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content="You are an academic advisor."),
        LLMMessage(role="user", content="What is ECE 391 about?"),
    ]


@pytest.mark.anyio
async def test_mock_client_returns_response_with_all_fields(sample_messages) -> None:
    client = MockLLMClient()

    response = await client.generate(sample_messages)

    assert isinstance(response, LLMResponse)
    assert response.content
    assert response.model == "mock-model"
    assert response.backend == BACKEND_MOCK
    assert response.latency_ms >= 0
    assert response.prompt_tokens is not None and response.prompt_tokens > 0
    assert response.completion_tokens is not None and response.completion_tokens > 0


@pytest.mark.anyio
async def test_mock_client_content_reflects_last_user_message() -> None:
    client = MockLLMClient()
    messages = [
        LLMMessage(role="system", content="be helpful"),
        LLMMessage(role="user", content="first user turn"),
        LLMMessage(role="assistant", content="prior answer"),
        LLMMessage(role="user", content="second user turn"),
    ]

    response = await client.generate(messages)

    assert "second user turn" in response.content
    assert "first user turn" not in response.content


@pytest.mark.anyio
async def test_mock_client_handles_only_system_messages() -> None:
    client = MockLLMClient()

    response = await client.generate(
        [LLMMessage(role="system", content="be terse")]
    )

    assert response.content  # does not crash
    assert "''" in response.content  # empty last-user echoed as ""


@pytest.mark.anyio
async def test_mock_client_reports_estimated_token_counts(sample_messages) -> None:
    client = MockLLMClient()

    response = await client.generate(sample_messages)

    # prompt_tokens roughly matches word count across all messages
    total_words = sum(len(msg.content.split()) for msg in sample_messages)
    assert response.prompt_tokens == max(1, total_words)


@pytest.mark.anyio
async def test_mock_client_uses_custom_model_name() -> None:
    client = MockLLMClient(model_name="llama-3.1-8b-instruct")

    response = await client.generate(
        [LLMMessage(role="user", content="hi")]
    )

    assert response.model == "llama-3.1-8b-instruct"
    assert "llama-3.1-8b-instruct" in response.content


@pytest.mark.anyio
async def test_mock_client_rejects_invalid_temperature() -> None:
    client = MockLLMClient()

    with pytest.raises(ValueError, match="temperature"):
        await client.generate(
            [LLMMessage(role="user", content="hi")], temperature=2.5
        )


@pytest.mark.anyio
async def test_mock_client_stream_yields_full_content_across_chunks(
    sample_messages,
) -> None:
    client = MockLLMClient()

    chunks = [chunk async for chunk in client.stream_generate(sample_messages)]

    joined = "".join(chunks)
    assert chunks, "stream must yield at least one chunk"
    assert len(chunks) > 1, "stream must split output across multiple chunks"
    assert "[mock stream backend=mock model=mock-model]" in joined
    assert "What is ECE 391 about?" in joined


@pytest.mark.anyio
async def test_mock_client_stream_rejects_invalid_temperature(
    sample_messages,
) -> None:
    client = MockLLMClient()

    with pytest.raises(ValueError, match="temperature"):
        async for _ in client.stream_generate(sample_messages, temperature=3.0):
            pass


@pytest.mark.anyio
async def test_mock_client_rejects_invalid_max_tokens() -> None:
    client = MockLLMClient()

    with pytest.raises(ValueError, match="max_tokens"):
        await client.generate(
            [LLMMessage(role="user", content="hi")], max_tokens=0
        )


def test_factory_defaults_to_mock_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    client = create_llm_client()

    assert isinstance(client, MockLLMClient)
    assert client.model_name == "mock-model"
    assert isinstance(client, LLMClient)  # Protocol structural check


def test_factory_reads_LLM_BACKEND_env_and_normalizes_case(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "  MOCK ")

    client = create_llm_client()

    assert isinstance(client, MockLLMClient)


def test_factory_reads_MODEL_NAME_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "mock")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5-1.5b-instruct")

    client = create_llm_client()

    assert client.model_name == "qwen2.5-1.5b-instruct"


def test_factory_explicit_arguments_override_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "mock")
    monkeypatch.setenv("MODEL_NAME", "env-model")

    client = create_llm_client(model_name="explicit-model")

    assert client.model_name == "explicit-model"


def test_factory_creates_vllm_remote_when_env_set(monkeypatch) -> None:
    from app.services.llm.vllm_backend import VLLMRemoteClient

    monkeypatch.setenv("LLM_BACKEND", BACKEND_VLLM_REMOTE)
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal:8000/")
    monkeypatch.setenv("VLLM_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_NAME", "Qwen2.5-7B-Instruct")

    client = create_llm_client()

    assert isinstance(client, VLLMRemoteClient)
    assert client.base_url == "http://vllm.internal:8000"  # trailing slash stripped
    assert client.api_key == "sk-test"
    assert client.model_name == "Qwen2.5-7B-Instruct"
    assert client.backend_name == BACKEND_VLLM_REMOTE


def test_factory_vllm_remote_raises_without_base_url(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", BACKEND_VLLM_REMOTE)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="VLLM_BASE_URL"):
        create_llm_client()


def test_factory_creates_external_debug_when_env_set(monkeypatch) -> None:
    from app.services.llm.vllm_backend import VLLMRemoteClient

    monkeypatch.setenv("LLM_BACKEND", BACKEND_EXTERNAL_DEBUG)
    monkeypatch.setenv("EXTERNAL_LLM_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("EXTERNAL_LLM_API_KEY", "sk-external")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini")

    client = create_llm_client()

    assert isinstance(client, VLLMRemoteClient)
    assert client.base_url == "https://api.example.com"
    assert client.api_key == "sk-external"
    assert client.backend_name == BACKEND_EXTERNAL_DEBUG


def test_factory_external_debug_falls_back_to_vllm_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", BACKEND_EXTERNAL_DEBUG)
    monkeypatch.delenv("EXTERNAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("EXTERNAL_LLM_API_KEY", raising=False)
    monkeypatch.setenv("VLLM_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("VLLM_API_KEY", "sk-fallback")

    client = create_llm_client()

    assert client.base_url == "https://api.example.com"
    assert client.api_key == "sk-fallback"
    assert client.backend_name == BACKEND_EXTERNAL_DEBUG


def test_factory_external_debug_raises_without_any_base_url(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", BACKEND_EXTERNAL_DEBUG)
    monkeypatch.delenv("EXTERNAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="EXTERNAL_LLM_BASE_URL"):
        create_llm_client()


def test_factory_raises_value_error_for_unknown_backend(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "gpt5")

    with pytest.raises(ValueError, match="Unknown LLM_BACKEND"):
        create_llm_client()


def test_llm_message_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="Invalid message role"):
        LLMMessage(role="tool", content="hi")


def test_llm_message_rejects_non_string_content() -> None:
    with pytest.raises(TypeError, match="content must be str"):
        LLMMessage(role="user", content=123)  # type: ignore[arg-type]


def test_llm_message_and_response_are_frozen() -> None:
    msg = LLMMessage(role="user", content="hi")
    response = LLMResponse(
        content="ok",
        model="m",
        backend="mock",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        msg.content = "changed"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        response.content = "changed"  # type: ignore[misc]
