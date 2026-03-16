from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "relay-dev"))

from amqp_binding import metadata_headers, queue_name_for_agent, routing_key_for_agent  # noqa: E402


VECTORS_DIR = ROOT / "sdks" / "tests" / "vectors" / "amqp"


def test_relay_amqp_fallback_fixture_matches_relay_header_and_routing_conventions() -> None:
    fixture_path = VECTORS_DIR / "relay_amqp_fallback_case.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    emitted = fixture["emitted_amqp_message"]
    body = emitted["serialized_body"]
    transport = emitted["transport_metadata"]

    assert metadata_headers(body) == transport["headers"]
    recipient = body["envelope"]["recipients"][0]
    assert routing_key_for_agent(recipient) == transport["routing_key"]
    assert queue_name_for_agent(recipient) == transport["queue"]
