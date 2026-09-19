from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_reports_explicit_sumo_state_before_start():
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ok"
    assert body["sumo"] in {"DISCONNECTED", "STARTING", "CONNECTED", "STOPPING", "ERROR"}
    if body["sumo"] == "DISCONNECTED":
        assert body["source"] is None


def test_status_exposes_backend_modules():
    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert {"sumo", "traci", "prediction", "classical_optimizer", "qaoa", "emergency", "incident_detection"} <= set(body)
