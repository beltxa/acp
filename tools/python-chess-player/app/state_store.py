from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable
from uuid import UUID

from .config import AppConfig
from .models import MatchState, StateEnvelope, utc_now


LOG = logging.getLogger(__name__)

Listener = Callable[[UUID], None]


class MatchStateStore:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._by_ucw_id: dict[UUID, MatchState] = {}
        self._listeners: list[Listener] = []
        self._load()

    def register_listener(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def _unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return _unsubscribe

    def list(self) -> list[MatchState]:
        with self._lock:
            values = [self._copy(item) for item in self._by_ucw_id.values()]
        values.sort(key=lambda state: state.createdAt or utc_now())
        return values

    def find(self, ucw_id: UUID) -> MatchState | None:
        with self._lock:
            state = self._by_ucw_id.get(ucw_id)
            return self._copy(state) if state is not None else None

    def upsert(self, state: MatchState | None) -> None:
        if state is None or state.ucwId is None:
            return
        notify_id: UUID | None = None
        with self._lock:
            next_state = self._copy(state)
            current = self._by_ucw_id.get(next_state.ucwId)
            if current is not None and self._equivalent_ignoring_updated_at(current, next_state):
                return
            next_state.updatedAt = utc_now()
            self._by_ucw_id[next_state.ucwId] = next_state
            self._persist()
            notify_id = next_state.ucwId

        if notify_id is not None:
            self._publish(notify_id)

    def remove(self, ucw_id: UUID) -> None:
        removed = False
        with self._lock:
            if ucw_id in self._by_ucw_id:
                self._by_ucw_id.pop(ucw_id, None)
                self._persist()
                removed = True
        if removed:
            self._publish(ucw_id)

    def _publish(self, ucw_id: UUID) -> None:
        listeners: list[Listener]
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(ucw_id)
            except Exception:
                LOG.debug("state listener failed", exc_info=True)

    def _state_path(self) -> Path:
        return Path(self._config.state_file)

    def _load(self) -> None:
        state_path = self._state_path()
        if not state_path.exists():
            return
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            envelope = StateEnvelope.model_validate(data)
            with self._lock:
                self._by_ucw_id.clear()
                for state in envelope.matches:
                    if state.ucwId is not None:
                        self._by_ucw_id[state.ucwId] = self._copy(state)
            LOG.info("Loaded %s chess match states from %s", len(self._by_ucw_id), state_path)
        except Exception:
            LOG.warning("Failed to load chess match state from %s", state_path, exc_info=True)

    def _persist(self) -> None:
        state_path = self._state_path()
        envelope = StateEnvelope(generated_at=utc_now(), matches=list(self._by_ucw_id.values()))
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(envelope.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
        except Exception:
            LOG.warning("Failed to persist chess match state to %s", state_path, exc_info=True)

    @staticmethod
    def _copy(state: MatchState | None) -> MatchState:
        if state is None:
            raise ValueError("state cannot be None")
        return MatchState.model_validate(state.model_dump())

    @staticmethod
    def _equivalent_ignoring_updated_at(left: MatchState, right: MatchState) -> bool:
        left_data = left.model_dump(mode="json")
        right_data = right.model_dump(mode="json")
        left_data["updatedAt"] = None
        right_data["updatedAt"] = None
        return left_data == right_data
