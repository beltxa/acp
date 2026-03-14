from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from acp.identity import AgentIdentity, write_identity
from acp.messages import DeliveryOutcome, DeliveryState, SendResult
from acp_cli.common import runtime_status_path
from acp_cli.main import main


def _seed_identity(
    storage_dir: Path,
    agent_id: str,
    *,
    direct_endpoint: str | None = None,
    relay_hints: list[str] | None = None,
    amqp: dict[str, object] | None = None,
    mqtt: dict[str, object] | None = None,
) -> None:
    identity = AgentIdentity.create(agent_id)
    document = identity.build_identity_document(
        direct_endpoint=direct_endpoint,
        relay_hints=relay_hints or [],
        amqp_service=amqp,
        mqtt_service=mqtt,
        trust_profile="self_asserted",
        capabilities={
            "agent_id": agent_id,
            "transports": ["direct", "relay", "amqp", "mqtt"],
            "supports": {"direct_delivery": True, "relay_delivery": True, "amqp_delivery": True, "mqtt_delivery": True},
        },
    )
    write_identity(storage_dir, identity, document)


def test_agent_run_invocation_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    captured: dict[str, object] = {}

    class FakeRuntime:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured["runtime_init"] = kwargs

        def run_forever(self) -> dict[str, object]:
            return {"processed_inbound": 0}

    def fake_load_or_create(agent_id: str, **kwargs):  # noqa: ANN003
        captured["agent_id"] = agent_id
        captured["agent_kwargs"] = kwargs
        return object()

    monkeypatch.setattr("acp_cli.agent_commands.AgentRuntime", FakeRuntime)
    monkeypatch.setattr("acp_cli.agent_commands.Agent.load_or_create", fake_load_or_create)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "agent",
            "run",
            "--agent-id",
            "agent:runner@localhost:9700",
            "--transport",
            "relay",
            "--port",
            "9700",
            "--relay",
            "http://relay.local:8080",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["agent_id"] == "agent:runner@localhost:9700"
    assert payload["effective_transports"] == ["direct", "relay"]
    runtime_init = captured["runtime_init"]
    assert runtime_init["transports"] == ["direct", "relay"]
    assert runtime_init["direct_port"] == 9700
    assert runtime_init["relay_url"] == "http://relay.local:8080"


def test_agent_status_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    agent_id = "agent:status.agent@localhost:9710"
    _seed_identity(
        tmp_path,
        agent_id,
        direct_endpoint="http://localhost:9710/api/v1/acp/messages",
        relay_hints=["http://relay.local:8080"],
    )

    status_file = runtime_status_path(tmp_path, agent_id)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(
        json.dumps(
            {
                "agent_id": agent_id,
                "pid": os.getpid(),
                "state": "running",
                "started_at": "2026-03-14T00:00:00Z",
                "last_activity_at": "2026-03-14T00:01:00Z",
                "transports": ["direct"],
                "updated_at": "2026-03-14T00:01:00Z",
            },
        ),
        encoding="utf-8",
    )

    class FakeRelayClient:
        def __init__(self, _relay_url: str) -> None:
            pass

        def discover_identity(self, _agent_id: str) -> dict[str, object]:
            return {"agent_id": agent_id, "service": {"direct_endpoint": "http://localhost:9710/api/v1/acp/messages"}}

    monkeypatch.setattr("acp_cli.agent_commands.RelayClient", FakeRelayClient)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "agent",
            "status",
            "--agent-id",
            agent_id,
            "--relay",
            "http://relay.local:8080",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["running"] is True
    assert payload["registration"]["registered"] is True
    assert payload["configured"]["service"]["direct_endpoint"] == "http://localhost:9710/api/v1/acp/messages"


def test_transport_list_output(tmp_path: Path, capsys) -> None:
    agent_id = "agent:transport.list@localhost:9720"
    _seed_identity(
        tmp_path,
        agent_id,
        direct_endpoint="http://localhost:9720/api/v1/acp/messages",
        relay_hints=["http://relay.local:8080"],
        amqp={"broker_url": "amqp://localhost:5672", "exchange": "acp.exchange"},
        mqtt={"broker_url": "mqtt://localhost:1883", "topic": "acp/agent/transport.list", "qos": 1},
    )

    code = main(["--storage-dir", str(tmp_path), "--json", "transport", "list", "--agent-id", agent_id])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["source"] == "local"
    assert "direct" in payload["supported_transports"]
    assert payload["service"]["amqp"]["broker_url"] == "amqp://localhost:5672"


def test_transport_probe_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    agent_id = "agent:transport.probe@localhost:9730"
    _seed_identity(
        tmp_path,
        agent_id,
        direct_endpoint="http://localhost:9730/api/v1/acp/messages",
        relay_hints=["http://relay.local:8080"],
        amqp={"broker_url": "amqp://localhost:5672", "exchange": "acp.exchange"},
        mqtt={"broker_url": "mqtt://localhost:1883", "topic": "acp/agent/transport.probe", "qos": 1},
    )

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    monkeypatch.setattr("acp_cli.transport_commands.requests.get", lambda *args, **kwargs: FakeResponse(200))

    class DummySocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

    monkeypatch.setattr("acp_cli.transport_commands.socket.create_connection", lambda *args, **kwargs: DummySocket())

    code = main(["--storage-dir", str(tmp_path), "--json", "transport", "probe", "--agent-id", agent_id])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    checks = {item["transport"]: item for item in payload["checks"]}
    assert checks["direct"]["reachable"] is True
    assert checks["relay"]["reachable"] is True
    assert checks["amqp"]["reachable"] is True
    assert checks["mqtt"]["reachable"] is True


def test_phase3_invalid_argument_handling(tmp_path: Path, capsys) -> None:
    code = main(["agent", "run"])
    assert code == 2
    assert "required" in capsys.readouterr().err.lower()

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "transport",
            "probe",
            "--agent-id",
            "agent:missing.identity",
        ],
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "transport_identity_not_found" in err


def test_message_capabilities_no_response_explicit_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    class FakeAgent:
        def request_capabilities(self, recipient: str):
            result = SendResult(
                operation_id="op-cap-no-response",
                message_id="msg-cap-no-response",
                message_ids=["msg-cap-no-response"],
                outcomes=[DeliveryOutcome(recipient=recipient, state=DeliveryState.DELIVERED)],
            )
            return result, None

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
    assert payload["capabilities"] is None
    assert payload["response_status"] == "request_sent_no_response"
