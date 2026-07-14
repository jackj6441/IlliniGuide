from fastapi.testclient import TestClient

from app.main import create_app


def test_metrics_endpoint_exposes_http_request_families() -> None:
    client = TestClient(create_app())

    response = client.get("/health")
    assert response.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    body = metrics.text
    assert "illiniguideserve_http_requests_total" in body
    assert "illiniguideserve_http_request_latency_seconds" in body


def test_metrics_record_client_errors() -> None:
    client = TestClient(create_app())

    response = client.get("/route-that-does-not-exist")
    assert response.status_code == 404

    body = client.get("/metrics").text
    assert "illiniguideserve_http_request_errors_total" in body
    assert 'method="GET"' in body
    assert 'status="404"' in body


def test_metrics_record_chat_tool_status_and_latency() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/chat",
        json={"message": "What is ECE 391 about?", "debug": True},
    )
    assert response.status_code == 200

    body = client.get("/metrics").text
    assert "illiniguideserve_tool_calls_total" in body
    assert 'tool="get_course_profile"' in body
    assert 'status="success"' in body
    assert "illiniguideserve_tool_latency_seconds" in body
    assert "illiniguideserve_retrieval_latency_seconds" in body
    assert "illiniguideserve_llm_latency_seconds" in body


def test_metrics_record_streaming_time_to_first_token() -> None:
    client = TestClient(create_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "What is ECE 391 about?"},
    ) as response:
        assert response.status_code == 200
        response.read()

    body = client.get("/metrics").text
    assert "illiniguideserve_stream_ttft_seconds" in body
    assert 'backend="mock"' in body
