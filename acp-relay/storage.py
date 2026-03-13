from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any


class MessageStore:
    def __init__(self) -> None:
        self._messages: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def save(
        self,
        *,
        message_id: str,
        operation_id: str,
        message: dict[str, Any],
        outcomes: list[dict[str, Any]],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            self._messages[message_id] = {
                "message_id": message_id,
                "operation_id": operation_id,
                "stored_at": now,
                "message": message,
                "outcomes": outcomes,
            }

    def get(self, message_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._messages.get(message_id)
