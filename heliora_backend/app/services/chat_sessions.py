"""In-memory chat session counters for scaffold-stage continuity."""

from __future__ import annotations

import threading


class InMemoryChatSessionStore:
    """Simple process-local session turn counter store."""

    def __init__(self) -> None:
        self._turn_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def record_turn(self, session_id: str) -> int:
        """Increase and return current turn index for a session."""
        with self._lock:
            current = self._turn_counts.get(session_id, 0) + 1
            self._turn_counts[session_id] = current
            return current

    def clear(self) -> None:
        """Clear all session state for tests."""
        with self._lock:
            self._turn_counts.clear()


chat_session_store = InMemoryChatSessionStore()
