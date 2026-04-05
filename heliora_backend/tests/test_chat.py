"""Chat endpoint tests."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.chat_sessions import chat_session_store


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_chat_sessions() -> Generator[None, None, None]:
    chat_session_store.clear()
    yield
    chat_session_store.clear()


def _chat_payload(content: str, session_id: str = "session_001") -> dict:
    return {
        "session_id": session_id,
        "content": content,
        "context": {"source": "test"},
    }


def test_chat_returns_intent_and_actions() -> None:
    response = client.post(
        "/api/v1/chat",
        json=_chat_payload("Please help me create a task plan for this week."),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["intent"] == "task_planning"
    assert "open_task_submit" in payload["data"]["suggested_actions"]
    assert payload["data"]["turn_index"] == 1


def test_chat_turn_index_increments_for_same_session() -> None:
    first = client.post("/api/v1/chat", json=_chat_payload("first message", session_id="s1"))
    second = client.post("/api/v1/chat", json=_chat_payload("second message", session_id="s1"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["turn_index"] == 1
    assert second.json()["data"]["turn_index"] == 2


def test_chat_rejects_blank_content_after_trim() -> None:
    response = client.post("/api/v1/chat", json=_chat_payload("   \n   "))

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


def test_chat_rejects_content_too_long() -> None:
    too_long = "x" * (settings.chat_max_content_chars + 1)
    response = client.post("/api/v1/chat", json=_chat_payload(too_long))

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "CONTENT_TOO_LONG"
    assert payload["details"]["max_chars"] == settings.chat_max_content_chars


def test_chat_trusted_local_max_restricted_for_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "security_policy_mode", "trusted_local_max")
    monkeypatch.setattr(settings, "local_max_privilege_ack", True)
    monkeypatch.setattr(settings, "local_max_privilege_loopback_only", True)

    response = client.post("/api/v1/chat", json=_chat_payload("hello"))

    assert response.status_code == 403
    assert response.json()["code"] == "SECURITY_MODE_RESTRICTED"
