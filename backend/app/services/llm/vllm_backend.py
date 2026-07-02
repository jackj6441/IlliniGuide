"""OpenAI-compatible remote backend used for both vLLM and external_debug.

This is a thin wrapper over ``POST /v1/chat/completions`` using ``httpx``.
It exists so route handlers, tools, and the answer synthesizer never talk
to an HTTP client directly — they go through the ``LLMClient`` Protocol
and the factory chooses this class when ``LLM_BACKEND`` is ``vllm_remote``
or ``external_debug``.

The class is deliberately small: one payload builder, one response parser,
one retry loop. Everything is testable without a running vLLM by injecting
``httpx.MockTransport``.
"""

import asyncio
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import httpx

from app.services.llm.client import (
    BACKEND_VLLM_REMOTE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    _validate_generate_kwargs,
)
from app.services.llm.schemas import LLMMessage, LLMResponse


CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_INITIAL_BACKOFF_SECONDS = 0.5

_RETRIABLE_HTTPX_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


class VLLMBackendError(Exception):
    """Base class for all errors raised by the remote LLM backend."""


class VLLMServerError(VLLMBackendError):
    """Server-side (5xx) or transport-layer error. Retriable."""


class VLLMClientError(VLLMBackendError):
    """Client-side (4xx) error. Never retried — retry cannot fix it."""


@dataclass
class VLLMRemoteClient:
    base_url: str
    model_name: str
    api_key: str | None = None
    backend_name: str = BACKEND_VLLM_REMOTE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> LLMResponse:
        _validate_generate_kwargs(temperature, max_tokens)

        payload = self._build_payload(messages, temperature, max_tokens)
        started_at = perf_counter()
        raw = await self._post_with_retry(payload)
        latency_ms = max(0, int((perf_counter() - started_at) * 1000))

        return self._parse_response(raw, latency_ms)

    def _build_payload(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in messages
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._post(payload)
                if response.status_code >= 500:
                    raise VLLMServerError(
                        f"vLLM server returned {response.status_code}: "
                        f"{response.text[:500]}"
                    )
                if response.status_code >= 400:
                    raise VLLMClientError(
                        f"vLLM server returned {response.status_code}: "
                        f"{response.text[:500]}"
                    )
                return response.json()
            except _RETRIABLE_HTTPX_ERRORS as exc:
                last_exc = VLLMServerError(f"transport error: {exc!r}")
            except VLLMServerError as exc:
                last_exc = exc
            # non-retriable exceptions (VLLMClientError, httpx.HTTPStatusError
            # from unexpected paths, plain exceptions) propagate immediately

            if attempt >= self.max_retries:
                assert last_exc is not None
                raise last_exc
            await asyncio.sleep(self.initial_backoff_seconds * (2 ** attempt))

        # loop always returns or raises, but keep type checkers happy
        assert last_exc is not None
        raise last_exc

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        client_kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": self.timeout_seconds,
        }
        if self.transport is not None:
            client_kwargs["transport"] = self.transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            return await client.post(
                CHAT_COMPLETIONS_PATH, json=payload, headers=self._headers()
            )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_response(
        self, raw: dict[str, Any], latency_ms: int
    ) -> LLMResponse:
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VLLMServerError(
                f"vLLM response missing choices/message/content: {raw!r}"
            ) from exc

        usage = raw.get("usage") or {}
        return LLMResponse(
            content=content,
            model=raw.get("model", self.model_name),
            backend=self.backend_name,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
