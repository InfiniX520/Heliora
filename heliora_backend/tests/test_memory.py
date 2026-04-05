"""Memory endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


client = TestClient(app)


def _payload(query: str, scope: str = "project", top_k: int = 5) -> dict:
    return {
        "query": query,
        "scope": scope,
        "top_k": top_k,
        "context": {"source": "test"},
    }


def test_memory_retrieve_returns_ranked_hits() -> None:
    response = client.post(
        "/api/v1/memory/retrieve",
        json=_payload("style relative path"),
    )

    assert response.status_code == 200
    body = response.json()
    memories = body["data"]["memories"]
    assert body["code"] == "OK"
    assert body["data"]["retrieval_mode"] == "rules_v1"
    assert len(memories) >= 1
    assert memories[0]["scope"] in {"project", "global"}
    assert body["data"]["injected_context"]


def test_memory_retrieve_respects_top_k() -> None:
    response = client.post(
        "/api/v1/memory/retrieve",
        json=_payload("task idempotency", top_k=1),
    )

    assert response.status_code == 200
    assert len(response.json()["data"]["memories"]) == 1


def test_memory_retrieve_rejects_blank_query_after_trim() -> None:
    response = client.post(
        "/api/v1/memory/retrieve",
        json=_payload("   \n  "),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


def test_memory_retrieve_rejects_query_too_long() -> None:
    too_long = "x" * (settings.memory_max_query_chars + 1)
    response = client.post(
        "/api/v1/memory/retrieve",
        json=_payload(too_long),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "QUERY_TOO_LONG"
    assert payload["details"]["max_chars"] == settings.memory_max_query_chars


def test_memory_retrieve_forbidden_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_memory_service", False)

    response = client.post(
        "/api/v1/memory/retrieve",
        json=_payload("style"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
