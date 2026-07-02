"""Smoke test for a locally running vLLM server.

Usage:
    .venv/bin/python -m scripts.verify_vllm
    .venv/bin/python -m scripts.verify_vllm --base-url http://localhost:8000 --model Qwen/Qwen2.5-7B-Instruct

Sends one small chat completion request through the ``LLMClient``
abstraction using the ``vllm_remote`` backend, prints latency and token
counts, and exits 0 on success / 1 on failure. Meant to be run right
after ``vllm serve`` finishes booting.
"""

import argparse
import asyncio
import os
import sys
from time import perf_counter

from app.services.llm import LLMMessage, create_llm_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
        help="Base URL of the vLLM server (default: %(default)s).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct"),
        help="Model name to send in the request payload.",
    )
    parser.add_argument(
        "--prompt",
        default="Say hi in exactly one sentence.",
        help="User prompt to send.",
    )
    return parser.parse_args()


async def _run(base_url: str, model: str, prompt: str) -> int:
    os.environ["LLM_BACKEND"] = "vllm_remote"
    os.environ["VLLM_BASE_URL"] = base_url
    os.environ["MODEL_NAME"] = model

    print(f"→ backend = vllm_remote")
    print(f"→ base_url = {base_url}")
    print(f"→ model = {model}")
    print(f"→ prompt = {prompt!r}")
    print()

    client = create_llm_client()
    messages = [
        LLMMessage(role="system", content="You are a UIUC academic advisor."),
        LLMMessage(role="user", content=prompt),
    ]

    started = perf_counter()
    try:
        response = await client.generate(messages, temperature=0.2, max_tokens=64)
    except Exception as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    wall_ms = int((perf_counter() - started) * 1000)

    print(f"OK — server returned {response.completion_tokens} tokens in "
          f"{response.latency_ms} ms (wall: {wall_ms} ms)")
    print(f"  model in response: {response.model}")
    print(f"  backend name:      {response.backend}")
    print(f"  prompt tokens:     {response.prompt_tokens}")
    print(f"  completion tokens: {response.completion_tokens}")
    print()
    print("--- content ---")
    print(response.content)
    print("---------------")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args.base_url, args.model, args.prompt))


if __name__ == "__main__":
    sys.exit(main())
