from datetime import timedelta

from fastapi.testclient import TestClient

from coordinator import main as main_module
from coordinator.main import app

client = TestClient(app)


def setup_function():
    main_module._metrics_store.clear()


def test_no_nodes_reported_yet():
    assert client.get("/nodes").json() == []


def test_report_and_list_metrics():
    resp = client.post(
        "/nodes/mac/metrics",
        json={"cpu_percent": 42.5, "mem_used_mb": 512, "mem_total_mb": 2048, "throughput_tokens_per_sec": 12.3},
    )
    assert resp.status_code == 200

    nodes = client.get("/nodes").json()
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "mac"
    assert nodes[0]["cpu_percent"] == 42.5
    assert nodes[0]["online"] is True


def test_partial_metrics_allowed():
    resp = client.post("/nodes/ubuntu/metrics", json={"cpu_percent": 10.0})
    assert resp.status_code == 200
    node = client.get("/nodes").json()[0]
    assert node["mem_used_mb"] is None
    assert node["throughput_tokens_per_sec"] is None


def test_node_marked_offline_after_stale_window():
    client.post("/nodes/mac/metrics", json={"cpu_percent": 1.0})
    # forzar que el ultimo reporte quede "viejo" sin esperar 30s de verdad
    main_module._metrics_store["mac"]["updated_at"] -= timedelta(seconds=60)

    node = client.get("/nodes").json()[0]
    assert node["online"] is False


def test_dashboard_renders_html():
    client.post("/nodes/mac/metrics", json={"cpu_percent": 33.3, "mem_used_mb": 100, "mem_total_mb": 200})
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "mac" in resp.text
    assert "33.3%" in resp.text


def test_dashboard_shows_empty_state():
    resp = client.get("/")
    assert "Ningún nodo reportó" in resp.text
