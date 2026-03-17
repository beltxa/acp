from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig  # noqa: E402
from storage import MessageStore  # noqa: E402
from test_crypto_helpers import attach_signed_sender, build_signed_identity_document  # noqa: E402


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


def _identity_document(agent_id: str, endpoint: str) -> dict[str, Any]:
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


def test_relay_store_and_forward_retries_then_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    sender_id = "agent:inventory.bot@localhost:9500"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="http://localhost:9500/acp/inbox",
    )
    recipient_id = "agent:shipping.bot@localhost:9501"
    resolver = RelayDiscoveryResolver(
        RelayRoutingConfig(
            default_scheme="http",
            timeout_seconds=1,
            allow_insecure_http=True,
        ),
    )
    resolver.register_identity_document(
        _identity_document(recipient_id, "http://localhost:9501/acp/inbox"),
    )
    store = MessageStore()
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store=store,
        store_and_forward=True,
        max_retry_attempts=3,
        retry_backoff_seconds=0.0,
        allow_insecure_http=True,
    )

    calls: list[int] = []

    def fake_post(
        url: str,
        json: dict[str, Any],
        timeout: int,
        verify: bool | str = True,
        cert: tuple[str, str] | None = None,
    ) -> DummyResponse:
        calls.append(1)
        if len(calls) == 1:
            raise requests.RequestException("temporary network failure")
        return DummyResponse(
            200,
            {
                "state": "ACKNOWLEDGED",
                "response_message": {
                    "envelope": {
                        "message_class": "ACK",
                    },
                },
            },
        )

    monkeypatch.setattr(requests, "post", fake_post)

    message = {
        "envelope": {
            "acp_version": "1.0",
            "message_class": "SEND",
            "message_id": "m-1",
            "operation_id": "op-1",
            "timestamp": "2026-03-13T10:00:00Z",
            "expires_at": "2026-03-13T10:10:00Z",
            "sender": sender_id,
            "recipients": [recipient_id],
            "context_id": "ctx-1",
            "crypto_suite": "ACP-AES256-GCM+X25519+ED25519",
        },
        "protected": {},
    }
    attach_signed_sender(
        message,
        sender_identity_document=sender_identity_document,
        sender_signing_private_key=sender_signing_private_key,
    )

    first_outcomes = router.route_message(message)
    assert first_outcomes[0]["state"] == "PENDING"
    assert store.pending_count() == 1

    store.save(
        message_id="m-1",
        operation_id="op-1",
        message=message,
        outcomes=first_outcomes,
    )

    processed = router.process_pending_deliveries(limit=10)
    assert processed[0]["state"] == "ACKNOWLEDGED"
    assert store.pending_count() == 0

    stored = store.get("m-1")
    assert stored is not None
    assert stored["outcomes"][0]["state"] == "ACKNOWLEDGED"
    assert stored["retry_history"]
