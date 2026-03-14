from __future__ import annotations

import json
from pathlib import Path

import pytest

from acp.messages import ACPMessage
from acp.mqtt_transport import MQTTTransport, topic_for_agent


ROOT = Path(__file__).resolve().parents[2]
VECTORS_DIR = ROOT / "tests" / "vectors" / "mqtt"

REQUIRED_FIXTURES = [
    "python_to_python_send.json",
    "java_to_python_send.json",
    "python_to_java_send.json",
    "multi_recipient_send_B.json",
    "multi_recipient_send_C.json",
    "multi_recipient_send_D.json",
    "duplicate_delivery_case.json",
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
def test_required_mqtt_fixture_exists(name: str) -> None:
    assert (VECTORS_DIR / name).is_file()


@pytest.mark.parametrize("name", STANDARD_MESSAGE_FIXTURES)
def test_standard_message_fixtures_match_mqtt_metadata_conventions(name: str) -> None:
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
    assert transport_metadata["topic"] == topic_for_agent(recipient)
    assert int(transport_metadata.get("qos", 1)) == 1

    properties = MQTTTransport._metadata_properties(body)  # noqa: SLF001
    assert transport_metadata["user_properties"] == properties


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
    assert MQTTTransport._metadata_properties(original_body) == original_transport["user_properties"]  # noqa: SLF001
