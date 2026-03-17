from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


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


def _base_message(sender_id: str, recipient_id: str) -> dict[str, Any]:
    return {
        "envelope": {
            "acp_version": "1.0",
            "message_class": "SEND",
            "message_id": "m-sign-1",
            "operation_id": "op-sign-1",
            "timestamp": "2026-03-13T10:00:00Z",
            "expires_at": "2026-03-13T10:10:00Z",
            "sender": sender_id,
            "recipients": [recipient_id],
            "context_id": "ctx-sign",
            "crypto_suite": "ACP-AES256-GCM+X25519+ED25519",
        },
        "protected": {},
    }


def test_relay_rejects_message_with_invalid_signature() -> None:
    sender_id = "agent:inventory.bot@localhost:9700"
    recipient_id = "agent:shipping.bot@localhost:9701"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="http://localhost:9700/acp/inbox",
    )

    resolver = RelayDiscoveryResolver(
        RelayRoutingConfig(default_scheme="http", timeout_seconds=1, allow_insecure_http=True),
    )
    resolver.register_identity_document(_recipient_identity(recipient_id, "http://localhost:9701/acp/inbox"))
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store_and_forward=False,
        allow_insecure_http=True,
    )

    message = _base_message(sender_id, recipient_id)
    attach_signed_sender(
        message,
        sender_identity_document=sender_identity_document,
        sender_signing_private_key=sender_signing_private_key,
    )
    message["protected"]["payload_hash"] = "tampered-after-signing"

    outcomes = router.route_message(message)
    assert len(outcomes) == 1
    assert outcomes[0]["state"] == "FAILED"
    assert outcomes[0]["reason_code"] == "INVALID_SIGNATURE"


def test_relay_rejects_invalid_sender_identity_document_signature() -> None:
    sender_id = "agent:inventory.bot@localhost:9700"
    recipient_id = "agent:shipping.bot@localhost:9701"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="http://localhost:9700/acp/inbox",
    )
    sender_identity_document["signature"]["value"] = "invalid-signature-value"

    resolver = RelayDiscoveryResolver(
        RelayRoutingConfig(default_scheme="http", timeout_seconds=1, allow_insecure_http=True),
    )
    resolver.register_identity_document(_recipient_identity(recipient_id, "http://localhost:9701/acp/inbox"))
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store_and_forward=False,
        allow_insecure_http=True,
    )

    message = _base_message(sender_id, recipient_id)
    attach_signed_sender(
        message,
        sender_identity_document=sender_identity_document,
        sender_signing_private_key=sender_signing_private_key,
    )

    outcomes = router.route_message(message)
    assert len(outcomes) == 1
    assert outcomes[0]["state"] == "FAILED"
    assert outcomes[0]["reason_code"] == "INVALID_SIGNATURE"
