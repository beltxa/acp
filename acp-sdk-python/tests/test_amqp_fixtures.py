from __future__ import annotations

import json
from pathlib import Path

import pytest

from acp.amqp_transport import AMQPTransport, queue_name_for_agent, routing_key_for_agent
from acp.messages import ACPMessage


ROOT = Path(__file__).resolve().parents[2]
VECTORS_DIR = ROOT / "tests" / "vectors" / "amqp"

REQUIRED_FIXTURES = [
    "python_to_python_send.json",
    "java_to_python_send.json",
    "python_to_java_send.json",
    "multi_recipient_send_B.json",
    "multi_recipient_send_C.json",
    "multi_recipient_send_D.json",
    "duplicate_delivery_case.json",
    "relay_amqp_fallback_case.json",
    "ack_example.json",
    "fail_example.json",
]

STANDARD_MESSAGE_FIXTURES = [
    "python_to_python_send.json",
    "java_to_python_send.json",
    "python_to_java_send.json",
    "multi_recipient_send_B.json",
    "multi_recipient_send_C.json",
    "multi_recipient_send_D.json",
    "ack_example.json",
    "fail_example.json",
]


def _load_fixture(name: str) -> dict[str, object]:
    path = VECTORS_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", REQUIRED_FIXTURES)
def test_required_amqp_fixture_exists(name: str) -> None:
    assert (VECTORS_DIR / name).is_file()


@pytest.mark.parametrize("name", STANDARD_MESSAGE_FIXTURES)
def test_standard_message_fixtures_match_amqp_metadata_conventions(name: str) -> None:
    fixture = _load_fixture(name)
    body = fixture["serialized_body"]
    assert isinstance(body, dict)
    ACPMessage.from_dict(body)

    envelope = body.get("envelope")
    assert isinstance(envelope, dict)
    recipients = envelope.get("recipients")
    assert isinstance(recipients, list) and len(recipients) == 1
    recipient = recipients[0]
    assert isinstance(recipient, str)

    transport_metadata = fixture["transport_metadata"]
    assert isinstance(transport_metadata, dict)

    headers = AMQPTransport._metadata_headers(body)
    assert headers == transport_metadata["headers"]
    assert routing_key_for_agent(recipient) == transport_metadata["routing_key"]
    assert queue_name_for_agent(recipient) == transport_metadata["queue"]


def test_duplicate_delivery_fixture_uses_same_message_id_for_original_and_duplicate() -> None:
    fixture = _load_fixture("duplicate_delivery_case.json")
    original = fixture["original_message"]
    duplicate = fixture["duplicate_message"]
    assert isinstance(original, dict)
    assert isinstance(duplicate, dict)

    original_body = original["serialized_body"]
    duplicate_body = duplicate["serialized_body"]
    assert isinstance(original_body, dict)
    assert isinstance(duplicate_body, dict)
    ACPMessage.from_dict(original_body)
    ACPMessage.from_dict(duplicate_body)

    original_envelope = original_body.get("envelope")
    duplicate_envelope = duplicate_body.get("envelope")
    assert isinstance(original_envelope, dict)
    assert isinstance(duplicate_envelope, dict)
    assert original_envelope["message_id"] == duplicate_envelope["message_id"]

    original_transport = original["transport_metadata"]
    assert isinstance(original_transport, dict)
    assert AMQPTransport._metadata_headers(original_body) == original_transport["headers"]


def test_relay_fallback_fixture_preserves_message_body_and_routing_metadata() -> None:
    fixture = _load_fixture("relay_amqp_fallback_case.json")
    input_message = fixture["input_acp_message"]
    emitted = fixture["emitted_amqp_message"]
    assert isinstance(input_message, dict)
    assert isinstance(emitted, dict)

    input_body = input_message["serialized_body"]
    emitted_body = emitted["serialized_body"]
    assert isinstance(input_body, dict)
    assert isinstance(emitted_body, dict)
    ACPMessage.from_dict(input_body)
    ACPMessage.from_dict(emitted_body)
    assert input_body == emitted_body

    transport = emitted["transport_metadata"]
    assert isinstance(transport, dict)
    assert AMQPTransport._metadata_headers(emitted_body) == transport["headers"]

    envelope = emitted_body.get("envelope")
    assert isinstance(envelope, dict)
    recipients = envelope.get("recipients")
    assert isinstance(recipients, list) and len(recipients) == 1
    recipient = recipients[0]
    assert isinstance(recipient, str)
    assert routing_key_for_agent(recipient) == transport["routing_key"]
    assert queue_name_for_agent(recipient) == transport["queue"]
