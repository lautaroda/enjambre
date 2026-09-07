import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DB_PATH", str(tmp_path / "test-ledger.db"))
    from ledger_daemon import main as main_module

    importlib.reload(main_module)
    with TestClient(main_module.app) as c:
        yield c


def test_register_node(client):
    resp = client.post("/nodes", json={"node_id": "node-a", "display_name": "Nodo A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == "node-a"
    assert body["display_name"] == "Nodo A"
    assert body["balance"] == 0


def test_unknown_node_returns_404(client):
    assert client.get("/nodes/does-not-exist").status_code == 404
    assert client.get("/nodes/does-not-exist/balance").status_code == 404
    assert client.get("/nodes/does-not-exist/usage").status_code == 404


def test_record_usage_credits_balance(client):
    client.post("/nodes", json={"node_id": "node-a"})

    resp = client.post(
        "/usage", json={"node_id": "node-a", "request_id": "req-1", "compute_units": 2.5}
    )
    assert resp.status_code == 200

    balance = client.get("/nodes/node-a/balance").json()
    assert balance["balance"] == 2.5

    resp2 = client.post(
        "/usage", json={"node_id": "node-a", "request_id": "req-2", "compute_units": 1.5}
    )
    assert resp2.status_code == 200

    balance = client.get("/nodes/node-a/balance").json()
    assert balance["balance"] == 4.0


def test_record_usage_is_idempotent_on_request_id(client):
    client.post("/nodes", json={"node_id": "node-a"})
    client.post(
        "/usage", json={"node_id": "node-a", "request_id": "req-dup", "compute_units": 5.0}
    )
    # Mismo request_id de nuevo (ej. reintento del verifier) - no debe acreditar doble.
    client.post(
        "/usage", json={"node_id": "node-a", "request_id": "req-dup", "compute_units": 5.0}
    )

    balance = client.get("/nodes/node-a/balance").json()
    assert balance["balance"] == 5.0

    history = client.get("/nodes/node-a/usage").json()
    assert len(history) == 1


def test_record_usage_auto_registers_unknown_node(client):
    resp = client.post(
        "/usage", json={"node_id": "brand-new-node", "request_id": "req-1", "compute_units": 3.0}
    )
    assert resp.status_code == 200

    node = client.get("/nodes/brand-new-node").json()
    assert node["balance"] == 3.0


def test_list_nodes_orders_by_balance_desc(client):
    client.post("/nodes", json={"node_id": "low"})
    client.post("/nodes", json={"node_id": "high"})
    client.post("/usage", json={"node_id": "low", "request_id": "r1", "compute_units": 1.0})
    client.post("/usage", json={"node_id": "high", "request_id": "r2", "compute_units": 10.0})

    nodes = client.get("/nodes").json()
    node_ids = [n["node_id"] for n in nodes]
    assert node_ids.index("high") < node_ids.index("low")


def test_rejects_non_positive_compute_units(client):
    client.post("/nodes", json={"node_id": "node-a"})
    resp = client.post(
        "/usage", json={"node_id": "node-a", "request_id": "req-1", "compute_units": 0}
    )
    assert resp.status_code == 422
