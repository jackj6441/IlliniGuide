from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import create_app


def override_db_session():
    yield None


app = create_app()
app.dependency_overrides[get_db_session] = override_db_session
client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_mock_response_shape() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "What is ECE 391 about?", "debug": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["citations"]
    assert body["citations"][0]["course_id"] == "ECE 391"
    assert body["used_tools"] == ["mock_intent_detector", "mock_keyword_retriever"]
    assert body["debug_trace"]["intent"] == "course_qa"
    assert isinstance(body["latency_ms"], int)


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
    assert body["citations"]


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
