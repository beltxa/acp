from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from acp import Agent, DeliveryState
from acp.amqp_transport import (
    build_amqp_service_hint,
    queue_name_for_agent,
    routing_key_for_agent,
)
from acp.messages import MessageClass


class FakeAMQPTransport:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(
        self,
        *,
        message: dict[str, Any],
        recipient_agent_id: str,
        amqp_service: dict[str, Any] | None = None,
    ) -> None:
        self.published.append(
            {
                "recipient": recipient_agent_id,
                "message": message,
                "amqp_service": dict(amqp_service or {}),
            },
        )


def _recipient_doc_with_amqp(recipient: Agent, broker_url: str) -> dict[str, Any]:
    doc = deepcopy(recipient.identity_document)
    service = dict(doc.get("service", {}))
    service["direct_endpoint"] = None
    service["amqp"] = build_amqp_service_hint(
        agent_id=recipient.agent_id,
        broker_url=broker_url,
        exchange="acp.exchange",
    )
    doc["service"] = service

    capabilities = dict(doc.get("capabilities", {}))
    capabilities["transports"] = ["amqp"]
    doc["capabilities"] = capabilities
    return doc


def test_amqp_queue_and_routing_key_conventions() -> None:
    agent_id = "agent:shipping.bot@companyB.com"
    assert queue_name_for_agent(agent_id) == "acp.agent.shipping.bot.companyB.com"
    assert routing_key_for_agent(agent_id) == "agent.shipping.bot.companyB.com"


def test_send_amqp_mode_publishes_one_message_per_recipient(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9400",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9400/acp/inbox",
        relay_url="http://localhost:8080",
        relay_hints=["http://localhost:8080"],
        discovery_scheme="http",
    )
    recipient1 = Agent.create(
        "agent:recipient1.bot@localhost:9401",
        storage_dir=tmp_path / "recipient1",
        endpoint="http://localhost:9401/acp/inbox",
        relay_url="http://localhost:8080",
        relay_hints=["http://localhost:8080"],
        discovery_scheme="http",
    )
    recipient2 = Agent.create(
        "agent:recipient2.bot@localhost:9402",
        storage_dir=tmp_path / "recipient2",
        endpoint="http://localhost:9402/acp/inbox",
        relay_url="http://localhost:8080",
        relay_hints=["http://localhost:8080"],
        discovery_scheme="http",
    )

    fake_transport = FakeAMQPTransport()
    sender.amqp_transport = fake_transport  # type: ignore[assignment]
    recipient_docs = {
        recipient1.agent_id: _recipient_doc_with_amqp(recipient1, "amqp://broker.local"),
        recipient2.agent_id: _recipient_doc_with_amqp(recipient2, "amqp://broker.local"),
    }

    sender.discovery.resolve = lambda agent_id: recipient_docs[agent_id]  # type: ignore[method-assign]

    result = sender.send(
        recipients=[recipient1.agent_id, recipient2.agent_id],
        payload={"type": "hand_start", "hand_id": "h-1"},
        context="ctx-amqp",
        delivery_mode="amqp",
    )

    assert len(fake_transport.published) == 2
    published_recipients = {item["recipient"] for item in fake_transport.published}
    assert published_recipients == {recipient1.agent_id, recipient2.agent_id}
    for item in fake_transport.published:
        envelope = item["message"]["envelope"]
        assert envelope["recipients"] == [item["recipient"]]
        assert item["amqp_service"]["routing_key"] == routing_key_for_agent(item["recipient"])

    assert len(result.message_ids or []) == 2
    assert all(outcome.state is DeliveryState.DELIVERED for outcome in result.outcomes)


def test_consume_from_amqp_acknowledges_duplicate_delivery(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9500",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9500/acp/inbox",
        discovery_scheme="http",
    )
    receiver = Agent.create(
        "agent:receiver.bot@localhost:9501",
        storage_dir=tmp_path / "receiver",
        endpoint="http://localhost:9501/acp/inbox",
        discovery_scheme="http",
    )

    receiver.identity_document["service"]["amqp"] = build_amqp_service_hint(
        agent_id=receiver.agent_id,
        broker_url="amqp://broker.local",
    )
    receiver_public_key = receiver.identity_document["keys"]["encryption"]["public_key"]
    outbound = sender._build_message(  # noqa: SLF001
        recipients=[receiver.agent_id],
        payload={"type": "ping"},
        recipient_public_keys={receiver.agent_id: receiver_public_key},
        message_class=MessageClass.SEND,
        context_id="ctx-consume",
        operation_id="op-consume",
        expires_in_seconds=60,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()

    class DuplicateDeliveryTransport:
        def __init__(self) -> None:
            self.acks: list[bool] = []

        def consume(
            self,
            *,
            agent_id: str,
            handler: Any,
            amqp_service: dict[str, Any] | None = None,
            max_messages: int | None = None,
        ) -> int:
            self.acks.append(bool(handler(outbound)))
            self.acks.append(bool(handler(outbound)))
            return 2

    fake_consumer = DuplicateDeliveryTransport()
    receiver.amqp_transport = fake_consumer  # type: ignore[assignment]
    receiver.discovery.resolve = lambda agent_id: sender.identity_document  # type: ignore[method-assign]

    consumed = receiver.consume_from_amqp(max_messages=2)
    assert consumed == 2
    assert fake_consumer.acks == [True, True]
