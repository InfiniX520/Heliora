"""Basic API smoke tests."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    """Health endpoint returns standard success envelope."""
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["code"] == "OK"
    assert payload["data"]["status"] == "healthy"
    assert payload["trace_id"]
