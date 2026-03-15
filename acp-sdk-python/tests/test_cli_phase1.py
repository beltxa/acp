from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from acp.capabilities import AgentCapabilities
from acp.discovery import DiscoveryClient
from acp.identity import AgentIdentity, read_identity
from acp_cli.main import build_parser, main


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


def test_parser_accepts_identity_and_discover_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(["identity", "create", "--agent-id", "agent:alice@localhost:9001"])
    assert args.domain == "identity"
    assert args.identity_command == "create"

    args = parser.parse_args(["discover", "get", "--agent-id", "agent:bob@localhost:9002"])
    assert args.domain == "discover"
    assert args.discover_command == "get"

    args = parser.parse_args(["discover", "well-known", "https://agent.example"])
    assert args.domain == "discover"
    assert args.discover_command == "well-known"


def test_version_flag_outputs_version(capsys) -> None:
    code = main(["--version"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("acp ")


def test_identity_create_and_show_json(tmp_path: Path, capsys) -> None:
    agent_id = "agent:test.identity@localhost:9100"
    code = main(["--storage-dir", str(tmp_path), "identity", "create", "--agent-id", agent_id])
    assert code == 0
    capsys.readouterr()

    assert read_identity(tmp_path, agent_id) is not None

    code = main(["--storage-dir", str(tmp_path), "--json", "identity", "show", "--agent-id", agent_id])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["agent_id"] == agent_id
    assert "public_keys" in payload
    dumped = json.dumps(payload)
    assert "signing_private_key" not in dumped
    assert "encryption_private_key" not in dumped


def test_identity_export_and_verify(tmp_path: Path, capsys) -> None:
    agent_id = "agent:test.export@localhost:9200"
    export_path = tmp_path / "exported" / "identity_document.json"

    assert main(["--storage-dir", str(tmp_path), "identity", "create", "--agent-id", agent_id]) == 0
    capsys.readouterr()

    assert main(
        [
            "--storage-dir",
            str(tmp_path),
            "identity",
            "export",
            "--agent-id",
            agent_id,
            "--out",
            str(export_path),
        ],
    ) == 0
    capsys.readouterr()
    assert export_path.exists()

    code = main(["--json", "identity", "verify", "--file", str(export_path)])
    assert code == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True

    tampered = json.loads(export_path.read_text(encoding="utf-8"))
    tampered["trust_profile"] = "invalid_profile"
    export_path.write_text(json.dumps(tampered), encoding="utf-8")
    code = main(["--json", "identity", "verify", "--file", str(export_path)])
    assert code == 1
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is False


def test_discover_get_and_list_from_cache(tmp_path: Path, capsys) -> None:
    target_id = "agent:discover.target"
    identity = AgentIdentity.create(target_id)
    identity_document = identity.build_identity_document(
        direct_endpoint="http://localhost:9999/api/v1/acp/messages",
        relay_hints=["http://localhost:8080"],
        trust_profile="self_asserted",
        capabilities=AgentCapabilities(agent_id=target_id).to_dict(),
    )

    cache_path = tmp_path / "discovery_cache.json"
    discovery = DiscoveryClient(cache_path=cache_path)
    discovery.seed(identity_document)

    code = main(["--storage-dir", str(tmp_path), "--json", "discover", "get", "--agent-id", target_id])
    assert code == 0
    get_payload = json.loads(capsys.readouterr().out)
    assert get_payload["ok"] is True
    assert get_payload["resolved"]["agent_id"] == target_id
    assert get_payload["resolved"]["service"]["direct_endpoint"] == "http://localhost:9999/api/v1/acp/messages"

    code = main(["--storage-dir", str(tmp_path), "--json", "discover", "list"])
    assert code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["ok"] is True
    assert list_payload["count"] == 1
    assert list_payload["entries"][0]["agent_id"] == target_id


def test_discover_well_known_command(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_id = "agent:wellknown.target@company.local"
    identity = AgentIdentity.create(target_id)
    identity_document = identity.build_identity_document(
        direct_endpoint="https://company.local/api/v1/acp/messages",
        relay_hints=["https://relay.company.local"],
        trust_profile="self_asserted",
        capabilities=AgentCapabilities(agent_id=target_id).to_dict(),
    )
    well_known = {
        "agent_id": target_id,
        "identity_document": "https://company.local/api/v1/acp/identity",
        "transports": {"http": {"endpoint": "https://company.local/api/v1/acp/messages"}},
        "version": "1.0",
        "security_profile": "https",
    }

    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if params is not None:
            return DummyResponse(404)
        if url == "https://company.local/.well-known/acp":
            return DummyResponse(200, well_known)
        if url == "https://company.local/api/v1/acp/identity":
            return DummyResponse(200, {"identity_document": identity_document})
        return DummyResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--json",
            "discover",
            "well-known",
            "https://company.local",
            "--agent-id",
            target_id,
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["well_known_url"] == "https://company.local/.well-known/acp"
    assert payload["well_known"]["agent_id"] == target_id
    assert payload["resolved"]["agent_id"] == target_id


def test_missing_argument_and_bad_argument_handling(tmp_path: Path, capsys) -> None:
    code = main(["identity", "create"])
    assert code == 2
    err = capsys.readouterr().err
    assert "required" in err.lower()

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "identity",
            "create",
            "--agent-id",
            "agent:test.bad@localhost:9300",
            "--trust-profile",
            "invalid_profile",
        ],
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "identity_create_failed" in err
