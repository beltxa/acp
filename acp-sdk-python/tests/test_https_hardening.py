from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from acp.identity import AgentIdentity, write_identity
from acp.transport import HTTPTransport, TransportError
from acp_cli.main import main


class _DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict[str, Any]:
        return self._body


def test_http_transport_rejects_insecure_http_by_default() -> None:
    transport = HTTPTransport()
    with pytest.raises(TransportError, match="insecure HTTP"):
        transport.post_json("http://localhost:8080/messages", {"x": 1})


def test_http_transport_accepts_https_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(method: str, url: str, **_kwargs: Any) -> _DummyResponse:
        assert method == "POST"
        assert url == "https://relay.example/messages"
        return _DummyResponse(200, {"status": "ok"})

    monkeypatch.setattr(requests, "request", fake_request)
    transport = HTTPTransport()
    response = transport.post_json("https://relay.example/messages", {"x": 1})
    assert response.status_code == 200


def test_cli_register_put_rejects_http_without_explicit_override(tmp_path: Path, capsys) -> None:
    agent_id = "agent:https.register@test"
    identity = AgentIdentity.create(agent_id)
    identity_document = identity.build_identity_document(
        direct_endpoint="https://agent.example/acp/messages",
        relay_hints=["https://relay.example"],
        trust_profile="self_asserted",
        capabilities={"agent_id": agent_id},
    )
    write_identity(tmp_path, identity, identity_document)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "register",
            "put",
            "--agent-id",
            agent_id,
            "--relay",
            "http://relay.local:8080",
            "--endpoint",
            "http://localhost:9999/acp/messages",
        ],
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "register_insecure_http" in err


def test_cli_config_validate_flags_insecure_http_by_default(tmp_path: Path, capsys) -> None:
    agent_id = "agent:https.validate@test"
    identity = AgentIdentity.create(agent_id)
    identity_document = identity.build_identity_document(
        direct_endpoint="http://localhost:9910/acp/messages",
        relay_hints=["http://localhost:8080"],
        trust_profile="self_asserted",
        capabilities={"agent_id": agent_id},
    )
    write_identity(tmp_path, identity, identity_document)

    code = main(["--storage-dir", str(tmp_path), "--json", "config", "validate"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["errors"]


def test_cli_config_validate_allows_http_with_explicit_override(tmp_path: Path, capsys) -> None:
    agent_id = "agent:https.validate.override@test"
    identity = AgentIdentity.create(agent_id)
    identity_document = identity.build_identity_document(
        direct_endpoint="http://localhost:9911/acp/messages",
        relay_hints=["http://localhost:8080"],
        trust_profile="self_asserted",
        capabilities={"agent_id": agent_id},
    )
    write_identity(tmp_path, identity, identity_document)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "--allow-insecure-http",
            "config",
            "validate",
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["warnings"]
