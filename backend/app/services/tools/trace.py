from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.schemas import DebugTrace


@dataclass(frozen=True)
class ToolCallTrace:
    tool_name: str
    arguments: dict[str, Any]
    status: str
    latency_ms: int
    error: str | None
    result_summary: dict[str, Any]


@dataclass
class ToolSpan:
    _result_summary: dict[str, Any] = field(default_factory=dict)

    def set_result_summary(self, summary: dict[str, Any]) -> None:
        self._result_summary = dict(summary)


class ToolTraceCollector:
    def __init__(self) -> None:
        self._intent: str | None = None
        self._tool_calls: list[ToolCallTrace] = []
        self._retrieved_chunks: list[dict[str, Any]] = []
        self._recommendation_scores: list[dict[str, Any]] = []
        self._notes: list[str] = []

    def set_intent(self, intent: str) -> None:
        self._intent = intent

    @contextmanager
    def time_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> Iterator[ToolSpan]:
        started_at = perf_counter()
        span = ToolSpan()
        try:
            yield span
        except Exception as exc:
            self._append_tool(
                tool_name=tool_name,
                arguments=arguments,
                started_at=started_at,
                status="error",
                error=str(exc),
                result_summary=span._result_summary,
            )
            raise
        else:
            self._append_tool(
                tool_name=tool_name,
                arguments=arguments,
                started_at=started_at,
                status="success",
                error=None,
                result_summary=span._result_summary,
            )

    def record_completed_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        status: str,
        latency_ms: int,
        result_summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Record a tool call whose timing was measured externally.

        Prefer ``time_tool`` when the operation is a single awaited call —
        it makes exception handling automatic. Use this method for streaming
        or other async iteration where wrapping in a context manager would
        interfere with generator control flow.
        """
        self._tool_calls.append(
            ToolCallTrace(
                tool_name=tool_name,
                arguments=dict(arguments),
                status=status,
                latency_ms=max(0, latency_ms),
                error=error,
                result_summary=dict(result_summary or {}),
            )
        )

    def record_skipped_tool(
        self, tool_name: str, arguments: dict[str, Any], reason: str
    ) -> None:
        self._tool_calls.append(
            ToolCallTrace(
                tool_name=tool_name,
                arguments=dict(arguments),
                status="skipped",
                latency_ms=0,
                error=None,
                result_summary={"reason": reason},
            )
        )

    def record_chunks(self, chunks: list[dict[str, Any]]) -> None:
        self._retrieved_chunks.extend(chunks)

    def record_recommendation_scores(self, scores: list[dict[str, Any]]) -> None:
        self._recommendation_scores.extend(scores)

    def add_note(self, note: str) -> None:
        self._notes.append(note)

    def tool_names(self) -> list[str]:
        return [call.tool_name for call in self._tool_calls]

    def notes(self) -> list[str]:
        return list(self._notes)

    def to_debug_trace(self) -> DebugTrace:
        return DebugTrace(
            intent=self._intent or "unknown",
            tool_calls=[
                {
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                    "status": call.status,
                    "latency_ms": call.latency_ms,
                    "error": call.error,
                    "result_summary": call.result_summary,
                }
                for call in self._tool_calls
            ],
            retrieved_chunks=list(self._retrieved_chunks),
            recommendation_scores=list(self._recommendation_scores),
        )

    def _append_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        started_at: float,
        status: str,
        error: str | None,
        result_summary: dict[str, Any],
    ) -> None:
        latency_ms = max(0, int((perf_counter() - started_at) * 1000))
        self._tool_calls.append(
            ToolCallTrace(
                tool_name=tool_name,
                arguments=dict(arguments),
                status=status,
                latency_ms=latency_ms,
                error=error,
                result_summary=dict(result_summary),
            )
        )
