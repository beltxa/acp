from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from acp import Agent, DeliveryState
from acp.messages import MessageClass
from acp.mqtt_transport import (
    agent_identifier_token,
    build_mqtt_service_hint,
    topic_for_agent,
)


class FakeMQTTTransport:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(
        self,
        *,
        message: dict[str, Any],
        recipient_agent_id: str,
        mqtt_service: dict[str, Any] | None = None,
    ) -> None:
        self.published.append(
            {
                "recipient": recipient_agent_id,
                "message": message,
                "mqtt_service": dict(mqtt_service or {}),
            },
        )


def _recipient_doc_with_mqtt(recipient: Agent, broker_url: str) -> dict[str, Any]:
    doc = deepcopy(recipient.identity_document)
    service = dict(doc.get("service", {}))
    service["direct_endpoint"] = None
    service["mqtt"] = build_mqtt_service_hint(
        agent_id=recipient.agent_id,
        broker_url=broker_url,
        qos=1,
    )
    doc["service"] = service

    capabilities = dict(doc.get("capabilities", {}))
    capabilities["transports"] = ["mqtt"]
    doc["capabilities"] = capabilities
    return doc


def _seed_local_mqtt_service(agent: Agent, broker_url: str) -> None:
    service = dict(agent.identity_document.get("service", {}))
    service["mqtt"] = build_mqtt_service_hint(
        agent_id=agent.agent_id,
        broker_url=broker_url,
        qos=1,
    )
    agent.identity_document["service"] = service


def test_mqtt_topic_and_identifier_normalization_is_stable() -> None:
    agent_id = "agent:Shipping.Bot@CompanyB.com"
    assert agent_identifier_token(agent_id) == "shipping.bot.companyb.com"
    assert topic_for_agent(agent_id) == "acp/agent/shipping.bot.companyb.com"


def test_send_mqtt_mode_publishes_one_message_per_recipient(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9800",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9800/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    recipient1 = Agent.create(
        "agent:recipient1.bot@localhost:9801",
        storage_dir=tmp_path / "recipient1",
        endpoint="http://localhost:9801/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    recipient2 = Agent.create(
        "agent:recipient2.bot@localhost:9802",
        storage_dir=tmp_path / "recipient2",
        endpoint="http://localhost:9802/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )

    fake_transport = FakeMQTTTransport()
    sender.mqtt_transport = fake_transport  # type: ignore[assignment]
    recipient_docs = {
        recipient1.agent_id: _recipient_doc_with_mqtt(recipient1, "mqtt://broker.local"),
        recipient2.agent_id: _recipient_doc_with_mqtt(recipient2, "mqtt://broker.local"),
    }
    sender.discovery.resolve = lambda agent_id: recipient_docs[agent_id]  # type: ignore[method-assign]

    result = sender.send(
        recipients=[recipient1.agent_id, recipient2.agent_id],
        payload={"type": "table_state", "table_id": "t-1"},
        context="ctx-mqtt",
        delivery_mode="mqtt",
    )

    assert len(fake_transport.published) == 2
    published_recipients = {item["recipient"] for item in fake_transport.published}
    assert published_recipients == {recipient1.agent_id, recipient2.agent_id}
    for item in fake_transport.published:
        envelope = item["message"]["envelope"]
        assert envelope["recipients"] == [item["recipient"]]
        wrapped = item["message"]["protected"]["wrapped_content_keys"]
        assert isinstance(wrapped, list) and len(wrapped) == 1
        assert wrapped[0]["recipient"] == item["recipient"]
        assert item["mqtt_service"]["topic"] == topic_for_agent(item["recipient"])

    assert len(result.message_ids or []) == 2
    assert all(outcome.state is DeliveryState.DELIVERED for outcome in result.outcomes)


def test_consume_from_mqtt_acknowledges_duplicate_delivery(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9810",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9810/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    receiver = Agent.create(
        "agent:receiver.bot@localhost:9811",
        storage_dir=tmp_path / "receiver",
        endpoint="http://localhost:9811/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    _seed_local_mqtt_service(sender, "mqtt://broker.local")
    _seed_local_mqtt_service(receiver, "mqtt://broker.local")

    receiver_public_key = receiver.identity_document["keys"]["encryption"]["public_key"]
    outbound = sender._build_message(  # noqa: SLF001
        recipients=[receiver.agent_id],
        payload={"type": "ping"},
        recipient_public_keys={receiver.agent_id: receiver_public_key},
        message_class=MessageClass.SEND,
        context_id="ctx-consume-mqtt",
        operation_id="op-consume-mqtt",
        expires_in_seconds=60,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()

    class DuplicateDeliveryTransport:
        def __init__(self) -> None:
            self.acks: list[bool] = []
            self.published: list[dict[str, Any]] = []

        def publish(
            self,
            *,
            message: dict[str, Any],
            recipient_agent_id: str,
            mqtt_service: dict[str, Any] | None = None,
        ) -> None:
            self.published.append(
                {
                    "recipient": recipient_agent_id,
                    "message": message,
                    "mqtt_service": dict(mqtt_service or {}),
                },
            )

        def consume(
            self,
            *,
            agent_id: str,
            handler: Any,
            mqtt_service: dict[str, Any] | None = None,
            max_messages: int | None = None,
            poll_timeout_seconds: float = 1.0,
        ) -> int:
            self.acks.append(bool(handler(outbound)))
            self.acks.append(bool(handler(outbound)))
            return 2

    fake_transport = DuplicateDeliveryTransport()
    receiver.mqtt_transport = fake_transport  # type: ignore[assignment]
    receiver.discovery.resolve = lambda agent_id: sender.identity_document  # type: ignore[method-assign]

    consumed = receiver.consume_from_mqtt(max_messages=2)
    assert consumed == 2
    assert fake_transport.acks == [True, True]
    assert len(fake_transport.published) == 2
    assert all(
        item["message"]["envelope"]["message_class"] == MessageClass.ACK.value
        for item in fake_transport.published
    )


def test_consume_from_mqtt_publishes_response_ack_to_sender(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9820",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9820/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    receiver = Agent.create(
        "agent:receiver.bot@localhost:9821",
        storage_dir=tmp_path / "receiver",
        endpoint="http://localhost:9821/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    _seed_local_mqtt_service(sender, "mqtt://broker.local")
    _seed_local_mqtt_service(receiver, "mqtt://broker.local")

    receiver_public_key = receiver.identity_document["keys"]["encryption"]["public_key"]
    outbound = sender._build_message(  # noqa: SLF001
        recipients=[receiver.agent_id],
        payload={"type": "ping"},
        recipient_public_keys={receiver.agent_id: receiver_public_key},
        message_class=MessageClass.SEND,
        context_id="ctx-consume-send-mqtt",
        operation_id="op-consume-send-mqtt",
        expires_in_seconds=60,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()

    class RoundTripTransport:
        def __init__(self) -> None:
            self.acks: list[bool] = []
            self.published: list[dict[str, Any]] = []

        def publish(
            self,
            *,
            message: dict[str, Any],
            recipient_agent_id: str,
            mqtt_service: dict[str, Any] | None = None,
        ) -> None:
            self.published.append(
                {
                    "recipient": recipient_agent_id,
                    "message": message,
                    "mqtt_service": dict(mqtt_service or {}),
                },
            )

        def consume(
            self,
            *,
            agent_id: str,
            handler: Any,
            mqtt_service: dict[str, Any] | None = None,
            max_messages: int | None = None,
            poll_timeout_seconds: float = 1.0,
        ) -> int:
            self.acks.append(bool(handler(outbound)))
            return 1

    fake_transport = RoundTripTransport()
    receiver.mqtt_transport = fake_transport  # type: ignore[assignment]
    receiver.discovery.resolve = lambda agent_id: sender.identity_document  # type: ignore[method-assign]

    consumed = receiver.consume_from_mqtt(max_messages=1)
    assert consumed == 1
    assert fake_transport.acks == [True]
    assert len(fake_transport.published) == 1
    published = fake_transport.published[0]
    assert published["recipient"] == sender.agent_id
    assert published["message"]["envelope"]["message_class"] == MessageClass.ACK.value
    assert published["mqtt_service"]["topic"] == topic_for_agent(sender.agent_id)


def test_handle_incoming_terminal_ack_and_fail_do_not_generate_response(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9830",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9830/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    responder = Agent.create(
        "agent:responder.bot@localhost:9831",
        storage_dir=tmp_path / "responder",
        endpoint="http://localhost:9831/acp/inbox",
        discovery_scheme="http",
        allow_insecure_http=True,
    )
    sender.discovery.resolve = lambda agent_id: responder.identity_document  # type: ignore[method-assign]

    sender_public_key = sender.identity_document["keys"]["encryption"]["public_key"]
    for message_class, payload in (
        (MessageClass.ACK, {"status": "accepted", "received_message_id": "m-original"}),
        (MessageClass.FAIL, {"reason_code": "POLICY_REJECTED", "detail": "failed"}),
    ):
        message = responder._build_message(  # noqa: SLF001
            recipients=[sender.agent_id],
            payload=payload,
            recipient_public_keys={sender.agent_id: sender_public_key},
            message_class=message_class,
            context_id=f"ctx-{message_class.value.lower()}",
            operation_id=f"op-{message_class.value.lower()}",
            expires_in_seconds=60,
            correlation_id="op-original",
            in_reply_to="m-original",
        ).to_dict()
        result = sender.handle_incoming(message)
        assert result["state"] == DeliveryState.ACKNOWLEDGED.value
        assert result["response_message"] is None
