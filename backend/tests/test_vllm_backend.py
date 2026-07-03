import httpx
import pytest

from app.services.llm.schemas import LLMMessage
from app.services.llm.vllm_backend import (
    CHAT_COMPLETIONS_PATH,
    VLLMClientError,
    VLLMRemoteClient,
    VLLMServerError,
)


def _openai_ok_body(content: str = "hello from vllm") -> dict:
    return {
        "id": "chat-1",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 12,
            "total_tokens": 54,
        },
    }


def _client(handler, **overrides) -> VLLMRemoteClient:
    """Build a VLLMRemoteClient wired to a MockTransport running ``handler``.

    Retries are made effectively instant by zeroing backoff so tests do not
    block on ``asyncio.sleep``.
    """
    defaults = dict(
        base_url="http://vllm.test",
        model_name="test-model",
        api_key=None,
        initial_backoff_seconds=0.0,
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    defaults.update(overrides)
    return VLLMRemoteClient(**defaults)


def _messages() -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content="be terse"),
        LLMMessage(role="user", content="hello"),
    ]


@pytest.mark.anyio
async def test_generate_success_parses_openai_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_ok_body("hello from vllm"))

    client = _client(handler)

    response = await client.generate(_messages())

    assert response.content == "hello from vllm"
    assert response.model == "test-model"
    assert response.backend == "vllm_remote"
    assert response.prompt_tokens == 42
    assert response.completion_tokens == 12
    assert response.latency_ms >= 0


@pytest.mark.anyio
async def test_generate_sends_openai_compatible_payload() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = request.read().decode()
        return httpx.Response(200, json=_openai_ok_body())

    client = _client(handler)

    await client.generate(_messages(), temperature=0.7, max_tokens=128)

    import json

    assert captured["url"].endswith(CHAT_COMPLETIONS_PATH)
    body = json.loads(captured["json"])
    assert body["model"] == "test-model"
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 128
    assert body["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hello"},
    ]
    assert captured["headers"]["content-type"] == "application/json"


@pytest.mark.anyio
async def test_generate_includes_bearer_token_when_api_key_set() -> None:
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(request.headers)
        return httpx.Response(200, json=_openai_ok_body())

    client = _client(handler, api_key="sk-secret-123")

    await client.generate(_messages())

    assert captured_headers["authorization"] == "Bearer sk-secret-123"


@pytest.mark.anyio
async def test_generate_omits_authorization_without_api_key() -> None:
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(request.headers)
        return httpx.Response(200, json=_openai_ok_body())

    client = _client(handler, api_key=None)

    await client.generate(_messages())

    assert "authorization" not in captured_headers


@pytest.mark.anyio
async def test_generate_reports_backend_name_for_external_debug() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_ok_body())

    client = _client(handler, backend_name="external_debug")

    response = await client.generate(_messages())

    assert response.backend == "external_debug"


@pytest.mark.anyio
async def test_generate_retries_on_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, text="upstream busy")
        return httpx.Response(200, json=_openai_ok_body("second try"))

    client = _client(handler)

    response = await client.generate(_messages())

    assert calls["n"] == 2
    assert response.content == "second try"


@pytest.mark.anyio
async def test_generate_retries_on_connect_error_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("dns dropped")
        return httpx.Response(200, json=_openai_ok_body("recovered"))

    client = _client(handler)

    response = await client.generate(_messages())

    assert calls["n"] == 2
    assert response.content == "recovered"


@pytest.mark.anyio
async def test_generate_does_not_retry_on_4xx() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    client = _client(handler)

    with pytest.raises(VLLMClientError, match="400"):
        await client.generate(_messages())

    assert calls["n"] == 1  # no retry


@pytest.mark.anyio
async def test_generate_raises_server_error_after_max_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="internal")

    client = _client(handler, max_retries=2)

    with pytest.raises(VLLMServerError, match="500"):
        await client.generate(_messages())

    assert calls["n"] == 3  # 1 initial + 2 retries


@pytest.mark.anyio
async def test_generate_rejects_invalid_temperature() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_ok_body())

    client = _client(handler)

    with pytest.raises(ValueError, match="temperature"):
        await client.generate(_messages(), temperature=3.0)


def _sse_chunk(delta: str) -> bytes:
    envelope = {
        "choices": [
            {"index": 0, "delta": {"content": delta}, "finish_reason": None}
        ]
    }
    import json as _json

    return f"data: {_json.dumps(envelope)}\n\n".encode()


def _sse_role_only_chunk() -> bytes:
    envelope = {
        "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
        ]
    }
    import json as _json

    return f"data: {_json.dumps(envelope)}\n\n".encode()


def _sse_stream_body(deltas: list[str], include_role_prefix: bool = True) -> bytes:
    parts: list[bytes] = []
    if include_role_prefix:
        parts.append(_sse_role_only_chunk())
    parts.extend(_sse_chunk(delta) for delta in deltas)
    parts.append(b"data: [DONE]\n\n")
    return b"".join(parts)


@pytest.mark.anyio
async def test_stream_generate_yields_deltas_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.read().decode())
        assert body["stream"] is True
        return httpx.Response(
            200,
            content=_sse_stream_body(["Hi", " there", ", welcome!"]),
            headers={"content-type": "text/event-stream"},
        )

    client = _client(handler)

    chunks = [chunk async for chunk in client.stream_generate(_messages())]

    assert chunks == ["Hi", " there", ", welcome!"]


@pytest.mark.anyio
async def test_stream_generate_skips_role_only_and_done_lines() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_sse_stream_body(["only-content"], include_role_prefix=True),
            headers={"content-type": "text/event-stream"},
        )

    client = _client(handler)

    chunks = [chunk async for chunk in client.stream_generate(_messages())]

    # Role-only prefix and terminal [DONE] must not surface as content
    assert chunks == ["only-content"]


@pytest.mark.anyio
async def test_stream_generate_raises_on_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream busy")

    client = _client(handler)

    with pytest.raises(VLLMServerError, match="503"):
        async for _ in client.stream_generate(_messages()):
            pass


@pytest.mark.anyio
async def test_stream_generate_raises_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad model")

    client = _client(handler)

    with pytest.raises(VLLMClientError, match="400"):
        async for _ in client.stream_generate(_messages()):
            pass


@pytest.mark.anyio
async def test_stream_generate_tolerates_malformed_json_line() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # A mix of a good chunk, a garbage line, another good chunk, and [DONE]
        body = (
            b"data: not-json\n\n"
            + _sse_chunk("A")
            + b"data: {}\n\n"  # valid JSON but missing choices
            + _sse_chunk("B")
            + b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    client = _client(handler)

    chunks = [chunk async for chunk in client.stream_generate(_messages())]

    assert chunks == ["A", "B"]


@pytest.mark.anyio
async def test_generate_raises_when_response_missing_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = _client(handler)

    with pytest.raises(VLLMServerError, match="missing choices"):
        await client.generate(_messages())
