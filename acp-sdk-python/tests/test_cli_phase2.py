from __future__ import annotations

import json
from pathlib import Path

import pytest

from acp.identity import AgentIdentity, read_identity, write_identity
from acp.messages import DeliveryOutcome, DeliveryState, SendResult
from acp_cli.main import main


def _seed_identity(storage_dir: Path, agent_id: str) -> None:
    identity = AgentIdentity.create(agent_id)
    document = identity.build_identity_document(
        direct_endpoint=None,
        relay_hints=[],
        trust_profile="self_asserted",
        capabilities={"agent_id": agent_id, "transports": ["direct", "relay", "amqp", "mqtt"]},
    )
    write_identity(storage_dir, identity, document)


def test_register_put_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    agent_id = "agent:register.put@localhost:9400"
    _seed_identity(tmp_path, agent_id)

    captured: dict[str, object] = {}

    class FakeRelayClient:
        def __init__(self, relay_url: str, **_kwargs: object) -> None:
            captured["relay"] = relay_url

        def register_identity_document(self, identity_document: dict[str, object]) -> dict[str, object]:
            captured["document"] = identity_document
            return {"status": "registered", "agent_id": identity_document.get("agent_id")}

    monkeypatch.setattr("acp_cli.register_commands.RelayClient", FakeRelayClient)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "--allow-insecure-http",
            "register",
            "put",
            "--agent-id",
            agent_id,
            "--relay",
            "http://relay.local:8080",
            "--endpoint",
            "http://localhost:9400/api/v1/acp/messages",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["agent_id"] == agent_id
    assert payload["relay"] == "http://relay.local:8080"
    assert payload["service"]["direct_endpoint"] == "http://localhost:9400/api/v1/acp/messages"
    relay_hints = payload["service"]["relay_hints"]
    assert "http://relay.local:8080" in relay_hints
    assert isinstance(captured.get("document"), dict)


def test_register_update_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    agent_id = "agent:register.update@localhost:9401"
    _seed_identity(tmp_path, agent_id)

    captured: dict[str, object] = {}

    class FakeRelayClient:
        def __init__(self, relay_url: str, **_kwargs: object) -> None:
            captured["relay"] = relay_url

        def register_identity_document(self, identity_document: dict[str, object]) -> dict[str, object]:
            captured["document"] = identity_document
            return {"status": "registered", "agent_id": identity_document.get("agent_id")}

    monkeypatch.setattr("acp_cli.register_commands.RelayClient", FakeRelayClient)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "--allow-insecure-http",
            "register",
            "update",
            "--agent-id",
            agent_id,
            "--relay",
            "http://relay.local:8080",
            "--transport",
            "mqtt",
            "--broker",
            "mqtt://localhost:1883",
            "--topic",
            "acp/agent/custom.topic",
            "--qos",
            "1",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    mqtt_service = payload["service"]["mqtt"]
    assert mqtt_service["broker_url"] == "mqtt://localhost:1883"
    assert mqtt_service["topic"] == "acp/agent/custom.topic"
    assert mqtt_service["qos"] == 1
    assert isinstance(captured.get("document"), dict)

    # Updated identity should remain locally readable after update.
    assert read_identity(tmp_path, agent_id) is not None


def test_register_show_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeRelayClient:
        def __init__(self, _: str, **_kwargs: object) -> None:
            pass

        def discover_identity(self, agent_id: str) -> dict[str, object]:
            return {
                "agent_id": agent_id,
                "trust_profile": "self_asserted",
                "valid_until": "2099-01-01T00:00:00Z",
                "service": {
                    "direct_endpoint": "http://localhost:9500/api/v1/acp/messages",
                    "relay_hints": ["http://relay.local:8080"],
                    "amqp": None,
                    "mqtt": None,
                },
            }

    monkeypatch.setattr("acp_cli.register_commands.RelayClient", FakeRelayClient)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "--allow-insecure-http",
            "register",
            "show",
            "--agent-id",
            "agent:show@test",
            "--relay",
            "http://relay.local:8080",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["service"]["direct_endpoint"] == "http://localhost:9500/api/v1/acp/messages"


def test_message_send_inline_json_with_multiple_recipients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def send(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            recipients = kwargs["recipients"]
            return SendResult(
                operation_id="op-1",
                message_id="msg-1",
                message_ids=["msg-1"],
                outcomes=[
                    DeliveryOutcome(recipient=recipient, state=DeliveryState.DELIVERED)
                    for recipient in recipients
                ],
            )

    def fake_load_or_create(agent_id: str, **kwargs):  # noqa: ANN003
        captured["agent_id"] = agent_id
        captured["agent_kwargs"] = kwargs
        return FakeAgent()

    monkeypatch.setattr("acp_cli.message_commands.Agent.load_or_create", fake_load_or_create)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "message",
            "send",
            "--from",
            "agent:sender@test",
            "--to",
            "agent:r1@test",
            "--to",
            "agent:r2@test",
            "--payload-json",
            '{"event":"move","uci":"e2e4"}',
            "--delivery-mode",
            "amqp",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["delivery_mode"] == "amqp"
    assert payload["recipients"] == ["agent:r1@test", "agent:r2@test"]
    assert captured["agent_id"] == "agent:sender@test"
    assert captured["recipients"] == ["agent:r1@test", "agent:r2@test"]
    assert captured["payload"] == {"event": "move", "uci": "e2e4"}


def test_message_send_payload_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    payload_file = tmp_path / "payload.json"
    payload_file.write_text('{"kind":"test","value":42}', encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeAgent:
        def send(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return SendResult(
                operation_id="op-2",
                message_id="msg-2",
                message_ids=["msg-2"],
                outcomes=[DeliveryOutcome(recipient="agent:r@test", state=DeliveryState.DELIVERED)],
            )

    monkeypatch.setattr(
        "acp_cli.message_commands.Agent.load_or_create",
        lambda *_args, **_kwargs: FakeAgent(),
    )

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "message",
            "send",
            "--from",
            "agent:sender@test",
            "--to",
            "agent:r@test",
            "--payload-file",
            str(payload_file),
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert captured["payload"] == {"kind": "test", "value": 42}


def test_message_capabilities_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeAgent:
        def request_capabilities(self, recipient: str):
            result = SendResult(
                operation_id="op-cap",
                message_id="msg-cap",
                message_ids=["msg-cap"],
                outcomes=[DeliveryOutcome(recipient=recipient, state=DeliveryState.ACKNOWLEDGED)],
            )
            return result, {"agent_id": recipient, "transports": ["direct", "relay"]}

    monkeypatch.setattr(
        "acp_cli.message_commands.Agent.load_or_create",
        lambda *_args, **_kwargs: FakeAgent(),
    )

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "message",
            "capabilities",
            "--from",
            "agent:sender@test",
            "--to",
            "agent:receiver@test",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["capabilities"]["agent_id"] == "agent:receiver@test"


def test_phase2_invalid_argument_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    # conflicting transport + delivery mode
    monkeypatch.setattr(
        "acp_cli.message_commands.Agent.load_or_create",
        lambda *_args, **_kwargs: object(),
    )
    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "message",
            "send",
            "--from",
            "agent:sender@test",
            "--to",
            "agent:r@test",
            "--payload-json",
            '{"x":1}',
            "--transport",
            "direct",
            "--delivery-mode",
            "relay",
        ],
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "Conflicting mode options" in err

    # invalid inline payload
    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "message",
            "send",
            "--from",
            "agent:sender@test",
            "--to",
            "agent:r@test",
            "--payload-json",
            '{"x":',
        ],
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "payload_parse_failed" in err
