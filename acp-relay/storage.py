from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
import uuid


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _parse_iso8601(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return datetime.max.replace(tzinfo=timezone.utc)


class MessageStore:
    def __init__(self) -> None:
        self._messages: dict[str, dict[str, Any]] = {}
        self._pending_retries: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def save(
        self,
        *,
        message_id: str,
        operation_id: str,
        message: dict[str, Any],
        outcomes: list[dict[str, Any]],
    ) -> None:
        now = _utc_now_iso()
        with self._lock:
            self._messages[message_id] = {
                "message_id": message_id,
                "operation_id": operation_id,
                "stored_at": now,
                "message": message,
                "outcomes": outcomes,
                "retry_history": [],
            }

    def get(self, message_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._messages.get(message_id)
            if value is None:
                return None
            return copy.deepcopy(value)

    def queue_retry(
        self,
        *,
        message_id: str,
        operation_id: str,
        recipient: str,
        endpoint: str,
        message: dict[str, Any],
        reason_code: str,
        detail: str,
        delay_seconds: float = 0.0,
        attempts: int = 1,
    ) -> str:
        pending_id = f"retry-{uuid.uuid4().hex}"
        next_attempt_at = (
            _utc_now() + timedelta(seconds=max(delay_seconds, 0.0))
        ).isoformat().replace("+00:00", "Z")
        record = {
            "pending_id": pending_id,
            "message_id": message_id,
            "operation_id": operation_id,
            "recipient": recipient,
            "endpoint": endpoint,
            "message": message,
            "attempts": attempts,
            "next_attempt_at": next_attempt_at,
            "reason_code": reason_code,
            "detail": detail,
            "created_at": _utc_now_iso(),
        }
        with self._lock:
            self._pending_retries[pending_id] = record
        return pending_id

    def claim_due_retries(self, *, limit: int = 20) -> list[dict[str, Any]]:
        now = _utc_now()
        with self._lock:
            due_ids = sorted(
                [
                    pending_id
                    for pending_id, value in self._pending_retries.items()
                    if _parse_iso8601(str(value.get("next_attempt_at", ""))) <= now
                ],
                key=lambda pending_id: _parse_iso8601(
                    str(self._pending_retries[pending_id].get("next_attempt_at", "")),
                ),
            )[:limit]
            claimed = [self._pending_retries.pop(pending_id) for pending_id in due_ids]
        return claimed

    def requeue_retry(
        self,
        record: dict[str, Any],
        *,
        delay_seconds: float,
        reason_code: str,
        detail: str,
    ) -> dict[str, Any]:
        updated = dict(record)
        updated["attempts"] = int(updated.get("attempts", 1)) + 1
        updated["next_attempt_at"] = (
            _utc_now() + timedelta(seconds=max(delay_seconds, 0.0))
        ).isoformat().replace("+00:00", "Z")
        updated["reason_code"] = reason_code
        updated["detail"] = detail
        with self._lock:
            self._pending_retries[str(updated["pending_id"])] = updated
        return updated

    def update_outcome(self, *, message_id: str, outcome: dict[str, Any]) -> None:
        with self._lock:
            stored = self._messages.get(message_id)
            if stored is None:
                return
            outcomes = stored.setdefault("outcomes", [])
            replaced = False
            for index, existing in enumerate(outcomes):
                if existing.get("recipient") == outcome.get("recipient"):
                    outcomes[index] = outcome
                    replaced = True
                    break
            if not replaced:
                outcomes.append(outcome)
            history = stored.setdefault("retry_history", [])
            history.append(
                {
                    "updated_at": _utc_now_iso(),
                    "outcome": outcome,
                },
            )

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending_retries)

    def list_pending(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            pending = sorted(
                self._pending_retries.values(),
                key=lambda item: _parse_iso8601(str(item.get("next_attempt_at", ""))),
            )[:limit]
            return [copy.deepcopy(item) for item in pending]
