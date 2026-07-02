from dataclasses import dataclass

import pytest

from app.services.answer_synthesis import LLM_TODO_SUFFIX, build_answer
from app.services.llm.schemas import LLMMessage, LLMResponse
from app.services.tools.dispatcher import DispatchedResults
from app.services.tools.schemas import (
    CourseProfile,
    RetrievedDoc,
    SearchCourseDocsResult,
)
from app.services.tools.trace import ToolTraceCollector


@dataclass
class _RecordingClient:
    backend_name: str = "recording"
    model_name: str = "test-model"
    received: list[list[LLMMessage]] = None
    fixed_content: str = "SYNTHESIZED ANSWER."

    def __post_init__(self) -> None:
        if self.received is None:
            self.received = []

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.received.append(list(messages))
        return LLMResponse(
            content=self.fixed_content,
            model=self.model_name,
            backend=self.backend_name,
            latency_ms=3,
            prompt_tokens=12,
            completion_tokens=8,
        )


@dataclass
class _FailingClient:
    backend_name: str = "failing"
    model_name: str = "test-model"

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> LLMResponse:
        raise RuntimeError("simulated LLM backend outage")


def _results_with_docs() -> DispatchedResults:
    return DispatchedResults(
        course_profiles={
            "ECE 391": CourseProfile(
                course_id="ECE 391",
                title="Systems Programming",
                description=None,
                credit_hours=None,
                prerequisites=None,
                career_tags=[],
                source_url=None,
            )
        },
        search_result=SearchCourseDocsResult(
            query="What is ECE 391?",
            course_ids=["ECE 391"],
            docs=[
                RetrievedDoc(
                    course_id="ECE 391",
                    source_name="Course Database",
                    source_url="https://example.com",
                    section_type="course_profile",
                    snippet="Systems programming, low-level C.",
                    score=0.5,
                )
            ],
            notes=[],
        ),
    )


@pytest.mark.anyio
async def test_build_answer_uses_llm_client() -> None:
    client = _RecordingClient(fixed_content="LLM SAID THIS.")
    collector = ToolTraceCollector()

    answer = await build_answer(
        "course_qa", "What is ECE 391?", _results_with_docs(), client, collector
    )

    assert answer == "LLM SAID THIS."
    assert len(client.received) == 1
    assert client.received[0][0].role == "system"
    assert client.received[0][1].role == "user"


@pytest.mark.anyio
async def test_build_answer_records_llm_call_in_trace() -> None:
    client = _RecordingClient()
    collector = ToolTraceCollector()

    await build_answer(
        "course_qa", "What is ECE 391?", _results_with_docs(), client, collector
    )

    trace = collector.to_debug_trace()
    assert trace.tool_calls
    llm_call = next(c for c in trace.tool_calls if c["tool_name"] == "llm_generate")
    assert llm_call["status"] == "success"
    assert llm_call["arguments"] == {
        "backend": "recording",
        "model": "test-model",
        "n_messages": 2,
    }
    assert llm_call["result_summary"]["prompt_tokens"] == 12
    assert llm_call["result_summary"]["completion_tokens"] == 8
    assert llm_call["result_summary"]["backend_latency_ms"] == 3


@pytest.mark.anyio
async def test_build_answer_falls_back_to_template_on_llm_error() -> None:
    collector = ToolTraceCollector()

    answer = await build_answer(
        "course_qa",
        "What is ECE 391?",
        _results_with_docs(),
        _FailingClient(),
        collector,
    )

    assert LLM_TODO_SUFFIX in answer  # template fallback marker
    assert "ECE 391" in answer  # fallback still uses evidence
    trace = collector.to_debug_trace()
    llm_call = next(c for c in trace.tool_calls if c["tool_name"] == "llm_generate")
    assert llm_call["status"] == "error"
    assert "simulated LLM backend outage" in llm_call["error"]


@pytest.mark.anyio
async def test_build_answer_fallback_note_is_recorded() -> None:
    collector = ToolTraceCollector()

    await build_answer(
        "course_qa",
        "What is ECE 391?",
        _results_with_docs(),
        _FailingClient(),
        collector,
    )

    notes = collector.notes()
    assert any("LLM call failed" in note for note in notes)
    assert any("template answer" in note for note in notes)


@pytest.mark.anyio
async def test_build_answer_fallback_handles_empty_results() -> None:
    collector = ToolTraceCollector()

    answer = await build_answer(
        "course_qa",
        "unknown course",
        DispatchedResults(),
        _FailingClient(),
        collector,
    )

    # Empty-evidence template branch reached
    assert "could not find enough evidence" in answer
    assert LLM_TODO_SUFFIX in answer


@pytest.mark.anyio
async def test_build_answer_unknown_intent_returns_default_template() -> None:
    collector = ToolTraceCollector()

    answer = await build_answer(
        "gibberish_intent",
        "hi",
        DispatchedResults(),
        _FailingClient(),
        collector,
    )

    assert "Unable to synthesize" in answer
