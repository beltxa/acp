from __future__ import annotations

import json

import pytest

from acp_cli.main import main


def test_relay_status_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeRelayClient:
        def __init__(self, _relay_url: str) -> None:
            pass

        def status(self) -> dict[str, object]:
            return {
                "status": "ok",
                "relay_version": "0.1.0",
                "registry_count": 3,
                "cache_count": 5,
                "store": {
                    "messages_total": 12,
                    "pending_deliveries_total": 2,
                },
                "routing": {
                    "store_and_forward": True,
                },
            }

    monkeypatch.setattr("acp_cli.relay_commands.RelayClient", FakeRelayClient)
    code = main(["--json", "relay", "status", "--relay", "http://relay.local:8080"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"]["status"] == "ok"
    assert payload["status"]["store"]["messages_total"] == 12


def test_relay_health_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeRelayClient:
        def __init__(self, _relay_url: str) -> None:
            pass

        def health(self) -> dict[str, str]:
            return {"status": "ok"}

    monkeypatch.setattr("acp_cli.relay_commands.RelayClient", FakeRelayClient)
    code = main(["relay", "health", "--relay", "http://relay.local:8080"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Relay health" in out
    assert "Status: ok" in out


def test_relay_registry_list_and_show(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    captured: dict[str, object] = {}

    class FakeRelayClient:
        def __init__(self, relay_url: str) -> None:
            captured["relay"] = relay_url

        def registry_list(self, *, limit: int = 100) -> dict[str, object]:
            captured["limit"] = limit
            return {
                "count": 1,
                "items": [
                    {
                        "agent_id": "agent:player1@localhost:8088",
                        "trust_profile": "self_asserted",
                    },
                ],
            }

        def registry_show(self, agent_id: str) -> dict[str, object]:
            captured["agent_id"] = agent_id
            return {
                "identity_document": {"agent_id": agent_id},
                "summary": {
                    "agent_id": agent_id,
                    "trust_profile": "self_asserted",
                    "valid_until": "2099-01-01T00:00:00Z",
                },
            }

    monkeypatch.setattr("acp_cli.relay_commands.RelayClient", FakeRelayClient)

    code = main(
        [
            "--json",
            "relay",
            "registry",
            "list",
            "--relay",
            "http://relay.local:8080",
            "--limit",
            "20",
        ],
    )
    assert code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["ok"] is True
    assert list_payload["count"] == 1
    assert captured["limit"] == 20

    code = main(
        [
            "--json",
            "relay",
            "registry",
            "show",
            "--relay",
            "http://relay.local:8080",
            "--agent-id",
            "agent:player1@localhost:8088",
        ],
    )
    assert code == 0
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload["ok"] is True
    assert show_payload["entry"]["summary"]["agent_id"] == "agent:player1@localhost:8088"
    assert captured["agent_id"] == "agent:player1@localhost:8088"


def test_relay_routes_show_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeRelayClient:
        def __init__(self, _relay_url: str) -> None:
            pass

        def routes_show(self, *, limit: int = 100) -> dict[str, object]:
            return {
                "routing": {"store_and_forward": True},
                "pending_count": 1,
                "pending": [
                    {
                        "pending_id": "retry-1",
                        "message_id": "msg-1",
                        "recipient": "agent:player2@localhost:8089",
                        "attempts": 1,
                    },
                ],
            }

    monkeypatch.setattr("acp_cli.relay_commands.RelayClient", FakeRelayClient)
    code = main(["--json", "relay", "routes", "show", "--relay", "http://relay.local:8080"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["routes"]["pending_count"] == 1
    assert payload["routes"]["pending"][0]["message_id"] == "msg-1"


def test_relay_ops_stats_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeRelayClient:
        def __init__(self, _relay_url: str) -> None:
            pass

        def ops_stats(self) -> dict[str, object]:
            return {
                "status": "ok",
                "store": {
                    "messages_total": 15,
                    "outcomes_total": 20,
                    "failure_outcomes_total": 2,
                    "pending_retries_total": 1,
                },
            }

    monkeypatch.setattr("acp_cli.relay_commands.RelayClient", FakeRelayClient)
    code = main(["--json", "relay", "ops", "stats", "--relay", "http://relay.local:8080"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["stats"]["store"]["failure_outcomes_total"] == 2


def test_relay_ops_failures_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeRelayClient:
        def __init__(self, _relay_url: str) -> None:
            pass

        def ops_failures(self, *, limit: int = 100) -> dict[str, object]:
            assert limit == 5
            return {
                "count": 1,
                "items": [
                    {
                        "message_id": "msg-fail",
                        "recipient": "agent:player4@localhost:8091",
                        "state": "FAILED",
                        "reason_code": "POLICY_REJECTED",
                    },
                ],
            }

    monkeypatch.setattr("acp_cli.relay_commands.RelayClient", FakeRelayClient)
    code = main(
        [
            "--json",
            "relay",
            "ops",
            "failures",
            "--relay",
            "http://relay.local:8080",
            "--limit",
            "5",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["state"] == "FAILED"


def test_phase4_json_output_and_argument_validation(capsys) -> None:
    code = main(["relay", "status"])
    assert code == 2
    err = capsys.readouterr().err
    assert "required" in err.lower()

    code = main(
        [
            "relay",
            "registry",
            "list",
            "--relay",
            "http://relay.local:8080",
            "--limit",
            "0",
        ],
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "positive integer" in err
