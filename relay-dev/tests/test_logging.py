from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig  # noqa: E402
from test_crypto_helpers import attach_signed_sender, build_signed_identity_document  # noqa: E402


def _recipient_identity(agent_id: str, endpoint: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "valid_until": "2099-01-01T00:00:00Z",
        "keys": {
            "signing": {"public_key": "sig-key"},
            "encryption": {"public_key": "enc-key"},
        },
        "service": {
            "direct_endpoint": endpoint,
            "relay_hints": [],
        },
    }


class _DummyResponse:
    status_code = 200

    @staticmethod
    def json() -> dict[str, Any]:
        return {
            "state": "ACKNOWLEDGED",
            "response_message": {"envelope": {"message_class": "ACK"}},
        }


def test_router_emits_delivery_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    sender_id = "agent:inventory.bot@localhost:9800"
    recipient_id = "agent:shipping.bot@localhost:9801"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="http://localhost:9800/acp/inbox",
    )

    resolver = RelayDiscoveryResolver(
        RelayRoutingConfig(default_scheme="http", timeout_seconds=1, allow_insecure_http=True),
    )
    resolver.register_identity_document(_recipient_identity(recipient_id, "http://localhost:9801/acp/inbox"))
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store_and_forward=False,
        allow_insecure_http=True,
    )

    def fake_post(
        url: str,
        json: dict[str, Any],
        timeout: int,
        verify: bool | str = True,
        cert: tuple[str, str] | None = None,
    ) -> _DummyResponse:
        return _DummyResponse()

    monkeypatch.setattr("routing.requests.post", fake_post)

    message = {
        "envelope": {
            "acp_version": "1.0",
            "message_class": "SEND",
            "message_id": "m-log-1",
            "operation_id": "op-log-1",
            "timestamp": "2026-03-13T10:00:00Z",
            "expires_at": "2026-03-13T10:10:00Z",
            "sender": sender_id,
            "recipients": [recipient_id],
            "context_id": "ctx-log",
            "crypto_suite": "ACP-AES256-GCM+X25519+ED25519",
        },
        "protected": {},
    }
    attach_signed_sender(
        message,
        sender_identity_document=sender_identity_document,
        sender_signing_private_key=sender_signing_private_key,
    )

    caplog.set_level(logging.INFO, logger="acp.relay.router")
    outcomes = router.route_message(message)
    assert outcomes[0]["state"] == "ACKNOWLEDGED"

    records = [record.getMessage() for record in caplog.records]
    assert any("route_message_start" in record for record in records)
    assert any("http_delivery_complete" in record for record in records)
    assert any("route_message_complete" in record for record in records)
