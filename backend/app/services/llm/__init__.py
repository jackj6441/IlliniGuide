"""LLM client abstraction.

This package defines the unified interface all backend LLM calls must go
through. The rest of the codebase depends on the ``LLMClient`` protocol and
never talks to a specific provider SDK directly. Backends are chosen at
construction time via ``create_llm_client`` (reads ``LLM_BACKEND`` env var).

Currently implemented backends:

- ``mock``: deterministic, no network, used for tests and local development
  before vLLM is available.

Planned backends (see ``docs/llm_serving_design.md``):

- ``vllm_remote``: OpenAI-compatible HTTP client against a self-hosted vLLM
  server (Task C3).
- ``external_debug``: OpenAI-compatible HTTP client against a public
  provider, used strictly as a debug fallback (not for production).
"""

from app.services.llm.client import (
    LLMClient,
    MockLLMClient,
    create_llm_client,
)
from app.services.llm.schemas import LLMMessage, LLMResponse
from app.services.llm.vllm_backend import (
    VLLMBackendError,
    VLLMClientError,
    VLLMRemoteClient,
    VLLMServerError,
)

__all__ = [
    "LLMClient",
    "LLMMessage",
    "LLMResponse",
    "MockLLMClient",
    "VLLMBackendError",
    "VLLMClientError",
    "VLLMRemoteClient",
    "VLLMServerError",
    "create_llm_client",
]
