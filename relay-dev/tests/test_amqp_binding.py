from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amqp_binding import queue_name_for_agent, routing_key_for_agent  # noqa: E402
from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig  # noqa: E402
from test_crypto_helpers import attach_signed_sender, build_signed_identity_document  # noqa: E402


class FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[dict[str, Any]] = []

    def publish(self, *, message: dict[str, Any], recipient: str, amqp_service: dict[str, Any]) -> None:
        if self.fail:
            from amqp_binding import AmqpRelayError

            raise AmqpRelayError("simulated amqp publish failure")
        self.published.append(
            {
                "recipient": recipient,
                "message": message,
                "amqp_service": dict(amqp_service),
            },
        )


def _identity_with_amqp(agent_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "valid_until": "2099-01-01T00:00:00Z",
        "keys": {
            "signing": {"public_key": "sig-key"},
            "encryption": {"public_key": "enc-key"},
        },
        "service": {
            "direct_endpoint": None,
            "relay_hints": [],
            "amqp": {
                "broker_url": "amqp://broker.local",
                "exchange": "acp.exchange",
                "queue": queue_name_for_agent(agent_id),
                "routing_key": routing_key_for_agent(agent_id),
            },
        },
    }


def test_amqp_route_tokens_include_namespace_when_present() -> None:
    agent_id = "agent:shipping.bot@localhost:9601"
    assert routing_key_for_agent(agent_id) == "agent.shipping.bot.localhost.9601"
    assert queue_name_for_agent(agent_id) == "acp.agent.shipping.bot.localhost.9601"
    assert routing_key_for_agent(agent_id, "namespace.alpha") == "agent.shipping.bot.localhost.9601.namespace.namespace.alpha"
    assert queue_name_for_agent(agent_id, "namespace.alpha") == "acp.agent.shipping.bot.localhost.9601.namespace.namespace.alpha"


def test_relay_routes_via_amqp_when_direct_endpoint_missing() -> None:
    sender_id = "agent:inventory.bot@localhost:9600"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="http://localhost:9600/acp/inbox",
    )
    recipient_id = "agent:shipping.bot@localhost:9601"
    resolver = RelayDiscoveryResolver(RelayRoutingConfig(default_scheme="http", timeout_seconds=1))
    resolver.register_identity_document(_identity_with_amqp(recipient_id))
    fake_publisher = FakePublisher()
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store_and_forward=False,
        amqp_publisher=fake_publisher,  # type: ignore[arg-type]
    )

    message = {
        "envelope": {
            "acp_version": "1.0",
            "message_class": "SEND",
            "message_id": "m-amqp-1",
            "operation_id": "op-amqp-1",
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

    outcomes = router.route_message(message)
    assert outcomes == [{"recipient": recipient_id, "state": "DELIVERED", "transport": "amqp"}]
    assert len(fake_publisher.published) == 1
    assert fake_publisher.published[0]["amqp_service"]["routing_key"] == routing_key_for_agent(recipient_id)


def test_relay_amqp_publish_failure_reports_failed_outcome() -> None:
    sender_id = "agent:inventory.bot@localhost:9600"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="http://localhost:9600/acp/inbox",
    )
    recipient_id = "agent:shipping.bot@localhost:9601"
    resolver = RelayDiscoveryResolver(RelayRoutingConfig(default_scheme="http", timeout_seconds=1))
    resolver.register_identity_document(_identity_with_amqp(recipient_id))
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store_and_forward=False,
        amqp_publisher=FakePublisher(fail=True),  # type: ignore[arg-type]
    )

    message = {
        "envelope": {
            "acp_version": "1.0",
            "message_class": "SEND",
            "message_id": "m-amqp-2",
            "operation_id": "op-amqp-2",
            "timestamp": "2026-03-13T10:00:00Z",
            "expires_at": "2026-03-13T10:10:00Z",
            "sender": sender_id,
            "recipients": [recipient_id],
            "context_id": "ctx-2",
            "crypto_suite": "ACP-AES256-GCM+X25519+ED25519",
        },
        "protected": {},
    }
    attach_signed_sender(
        message,
        sender_identity_document=sender_identity_document,
        sender_signing_private_key=sender_signing_private_key,
    )

    outcomes = router.route_message(message)
    assert len(outcomes) == 1
    assert outcomes[0]["recipient"] == recipient_id
    assert outcomes[0]["state"] == "FAILED"
    assert outcomes[0]["reason_code"] == "POLICY_REJECTED"
    assert "simulated amqp publish failure" in outcomes[0]["detail"]
