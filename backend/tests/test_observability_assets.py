import json
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]


def test_prometheus_config_scrapes_backend_and_vllm() -> None:
    config = (REPO_ROOT / "infra/prometheus/prometheus.yml").read_text()

    assert "job_name: illiniguideserve-backend" in config
    assert "job_name: vllm" in config
    assert "metrics_path: /metrics" in config
    assert "host.docker.internal:8001" in config
    assert "host.docker.internal:8000" in config


def test_grafana_dashboard_contains_application_and_vllm_panels() -> None:
    dashboard_path = REPO_ROOT / "infra/grafana/dashboards/illiniguideserve.json"
    dashboard = json.loads(dashboard_path.read_text())
    titles = {panel["title"] for panel in dashboard["panels"]}

    assert dashboard["uid"] == "illiniguideserve-serving"
    assert "HTTP request rate" in titles
    assert "HTTP p95 latency" in titles
    assert "Streaming TTFT p95" in titles
    assert "vLLM waiting requests" in titles
    assert "vLLM KV-cache usage" in titles
