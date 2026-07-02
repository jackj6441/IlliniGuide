from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import create_app


class _EmptyScalars:
    def all(self):
        return []


class _EmptyFakeSession:
    """Minimal session stand-in used across API tests.

    Real tools receive this session; scalar/scalars return empty results so
    DB-backed lookups produce None/empty output but do not crash. The
    ``search_course_docs`` tool then falls back to in-memory sample chunks,
    which keeps citation shape stable in tests without a real Postgres.
    """

    def scalar(self, statement):
        return None

    def scalars(self, statement):
        return _EmptyScalars()


def override_db_session():
    yield _EmptyFakeSession()


app = create_app()
app.dependency_overrides[get_db_session] = override_db_session
client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_course_qa_runs_router_tools_and_llm() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "What is ECE 391 about?", "debug": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    # Mock LLM prefix proves the answer came from the LLM path, not the template
    assert "[mock backend=" in body["answer"]
    assert body["citations"]
    assert body["citations"][0]["course_id"] == "ECE 391"
    assert body["used_tools"] == [
        "get_course_profile",
        "search_course_docs",
        "llm_generate",
    ]
    assert body["debug_trace"]["intent"] == "course_qa"
    assert isinstance(body["latency_ms"], int)


def test_chat_debug_trace_contains_per_tool_latency_and_status() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "What is ECE 391 about?", "debug": True},
    )

    tool_calls = response.json()["debug_trace"]["tool_calls"]
    assert tool_calls
    for call in tool_calls:
        assert set(call.keys()) >= {
            "tool_name",
            "arguments",
            "status",
            "latency_ms",
            "error",
            "result_summary",
        }
        assert call["status"] in {"success", "error", "skipped"}
        assert isinstance(call["latency_ms"], int)
        assert call["latency_ms"] >= 0


def test_chat_llm_generate_call_captures_backend_metadata() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "What is ECE 391 about?", "debug": True},
    )

    tool_calls = response.json()["debug_trace"]["tool_calls"]
    llm_call = next(c for c in tool_calls if c["tool_name"] == "llm_generate")
    assert llm_call["status"] == "success"
    assert llm_call["arguments"]["backend"] == "mock"
    assert llm_call["result_summary"]["prompt_tokens"] > 0
    assert llm_call["result_summary"]["completion_tokens"] > 0


def test_chat_omits_debug_trace_when_debug_flag_is_false() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "What is ECE 391 about?"},
    )

    body = response.json()
    assert body["debug_trace"] is None
    assert body["used_tools"], "used_tools should still be populated when debug is off"


def test_chat_comparison_routes_and_invokes_compare_courses() -> None:
    response = client.post(
        "/api/chat",
        json={
            "message": "Compare ECE 408 and CS 433 for AI infra",
            "debug": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["debug_trace"]["intent"] == "comparison"
    assert "compare_courses" in body["used_tools"]
    assert body["used_tools"].count("get_course_profile") == 2
    assert body["used_tools"].count("get_gpa_stats") == 2
    assert body["used_tools"][-1] == "llm_generate"


def test_chat_recommendation_routes_and_invokes_recommend_courses() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "What courses are good for AI infra?", "debug": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["debug_trace"]["intent"] == "recommendation"
    assert "recommend_courses" in body["used_tools"]
    assert body["used_tools"][-1] == "llm_generate"


def test_chat_prereq_check_routes_and_invokes_check_prerequisites() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "Am I ready for ECE 408?", "debug": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["debug_trace"]["intent"] == "prereq_check"
    assert "check_prerequisites" in body["used_tools"]
    assert body["used_tools"][-1] == "llm_generate"


def test_compare_requires_at_least_two_courses() -> None:
    response = client.post(
        "/api/compare",
        json={"course_ids": ["ECE 408"], "dimension": "ai_infra"},
    )

    assert response.status_code == 422


def test_compare_returns_mock_response_shape() -> None:
    response = client.post(
        "/api/compare",
        json={"course_ids": ["ECE 408", "CS 433"], "dimension": "ai_infra"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]
    assert len(body["courses"]) == 2
    assert body["comparison"]["status"] == "mocked"


def test_recommend_returns_mock_response_shape() -> None:
    response = client.post(
        "/api/recommend",
        json={
            "target_direction": "ai_infra",
            "completed_courses": ["ECE 385"],
            "max_results": 5,
            "debug": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"]
    assert body["debug_scores"][0]["status"] == "mocked"
