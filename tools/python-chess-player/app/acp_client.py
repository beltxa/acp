from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import ChessPayloadEvent

try:
    from acp import Agent, DeliveryState
except ModuleNotFoundError:  # pragma: no cover - fallback for local workspace execution
    repo_root = Path(__file__).resolve().parents[3]
    sdk_path = repo_root / "acp-sdk-python"
    if sdk_path.exists():
        sys.path.insert(0, str(sdk_path))
    from acp import Agent, DeliveryState


LOG = logging.getLogger(__name__)


class AcpChessClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._delivery_mode = self._parse_delivery_mode(config.acp_delivery_mode)
        self._agent = self._build_agent()

    def get_local_agent_id(self) -> str:
        return self._config.local_agent_id

    def get_identity_document(self) -> dict[str, Any]:
        return dict(self._agent.identity_document)

    def receive(self, raw_message: dict[str, Any]) -> dict[str, Any]:
        return self._agent.handle_incoming(raw_message)

    def send_chess_event(self, event: ChessPayloadEvent) -> bool:
        if event is None:
            return False
        payload = event.to_payload_dict()
        result = self._agent.send(
            recipients=[self._config.remote_agent_id],
            payload=payload,
            context=f"chess:{event.match_id}",
            delivery_mode=self._delivery_mode,
        )
        outcomes = getattr(result, "outcomes", None) or []
        if not outcomes:
            return False

        for outcome in outcomes:
            state = getattr(outcome, "state", None)
            if state in {DeliveryState.ACKNOWLEDGED, DeliveryState.DELIVERED}:
                return True

        first = outcomes[0]
        LOG.warning(
            "ACP send failed: recipient=%s state=%s reasonCode=%s detail=%s",
            getattr(first, "recipient", None),
            getattr(getattr(first, "state", None), "value", getattr(first, "state", None)),
            getattr(first, "reason_code", None),
            getattr(first, "detail", None),
        )
        return False

    def _build_agent(self) -> Agent:
        kwargs: dict[str, Any] = {
            "storage_dir": self._config.acp_storage_dir,
            "endpoint": self._config.resolve_acp_endpoint(),
            "discovery_scheme": self._config.acp_discovery_scheme,
        }
        if self._config.acp_relay_url:
            kwargs["relay_url"] = self._config.acp_relay_url
            kwargs["relay_hints"] = [self._config.acp_relay_url]
        return Agent.load_or_create(self._config.local_agent_id, **kwargs)

    @staticmethod
    def _parse_delivery_mode(configured: str | None) -> str:
        normalized = (configured or "direct").strip().lower()
        if normalized in {"auto", "direct", "relay", "amqp", "mqtt"}:
            return normalized
        return "direct"
