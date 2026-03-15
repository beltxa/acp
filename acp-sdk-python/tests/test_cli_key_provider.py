from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from acp.identity import AgentIdentity, write_identity
from acp.key_provider import VaultKeyProvider
from acp.messages import DeliveryOutcome, DeliveryState, SendResult
from acp_cli.main import main


def _seed_identity(storage_dir: Path, agent_id: str) -> None:
    identity = AgentIdentity.create(agent_id)
    identity_document = identity.build_identity_document(
        direct_endpoint="https://localhost:8443/api/v1/acp/messages",
        relay_hints=["https://relay.example"],
        trust_profile="self_asserted",
        capabilities={"agent_id": agent_id, "transports": ["direct", "relay"]},
    )
    write_identity(storage_dir, identity, identity_document)


def test_identity_show_reports_local_key_provider(tmp_path: Path, capsys) -> None:
    agent_id = "agent:key.local.show@demo"
    _seed_identity(tmp_path, agent_id)

    code = main(["--storage-dir", str(tmp_path), "--json", "identity", "show", "--agent-id", agent_id])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["key_provider"]["provider"] == "local"


def test_identity_show_reports_vault_provider_metadata(tmp_path: Path, capsys) -> None:
    agent_id = "agent:key.vault.show@demo"
    _seed_identity(tmp_path, agent_id)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--key-provider",
            "vault",
            "--vault-url",
            "https://vault.example",
            "--vault-path",
            "secret/data/acp/identities",
            "--json",
            "identity",
            "show",
            "--agent-id",
            agent_id,
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["key_provider"]["provider"] == "vault"
    assert payload["key_provider"]["vault_url"] == "https://vault.example"
    assert payload["key_provider"]["vault_path"] == "secret/data/acp/identities"


def test_message_send_passes_vault_key_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def send(self, **kwargs: Any) -> SendResult:
            captured["send_kwargs"] = kwargs
            recipients = kwargs["recipients"]
            return SendResult(
                operation_id="op-vault",
                message_id="msg-vault",
                message_ids=["msg-vault"],
                outcomes=[DeliveryOutcome(recipient=item, state=DeliveryState.DELIVERED) for item in recipients],
            )

    def fake_load_or_create(agent_id: str, **kwargs: Any) -> FakeAgent:
        captured["agent_id"] = agent_id
        captured["agent_kwargs"] = kwargs
        return FakeAgent()

    monkeypatch.setattr("acp_cli.message_commands.Agent.load_or_create", fake_load_or_create)

    code = main(
        [
            "--storage-dir",
            str(tmp_path),
            "--key-provider",
            "vault",
            "--vault-url",
            "https://vault.example",
            "--vault-path",
            "secret/data/acp/identities",
            "--json",
            "message",
            "send",
            "--from",
            "agent:sender@demo",
            "--to",
            "agent:receiver@demo",
            "--payload-json",
            '{"kind":"ping"}',
        ],
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    provider = captured["agent_kwargs"]["key_provider"]
    assert isinstance(provider, VaultKeyProvider)
    assert provider.vault_url == "https://vault.example"
    assert provider.vault_path == "secret/data/acp/identities"


def test_agent_status_reports_key_provider(tmp_path: Path, capsys) -> None:
    agent_id = "agent:key.status@demo"
    _seed_identity(tmp_path, agent_id)

    code = main(["--storage-dir", str(tmp_path), "--json", "agent", "status", "--agent-id", agent_id])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["key_provider"]["provider"] == "local"


def test_vault_key_provider_missing_required_config_is_rejected(capsys) -> None:
    code = main(["--key-provider", "vault", "config", "show"])
    assert code == 2
    err = capsys.readouterr().err
    assert "config_invalid_key_provider" in err


def test_vault_provider_mtls_without_local_cert_files_is_allowed(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage_dir": str(tmp_path / "data"),
                "key_provider": "vault",
                "vault_url": "https://vault.example",
                "vault_path": "secret/data/acp/identities",
                "mtls_enabled": True,
            },
        ),
        encoding="utf-8",
    )

    code = main(["--config", str(config_path), "--json", "config", "validate"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_vault_provider_mtls_rejects_partial_local_cert_override(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage_dir": str(tmp_path / "data"),
                "key_provider": "vault",
                "vault_url": "https://vault.example",
                "vault_path": "secret/data/acp/identities",
                "mtls_enabled": True,
                "cert_file": "/tmp/client-cert.pem",
            },
        ),
        encoding="utf-8",
    )

    code = main(["--config", str(config_path), "--json", "config", "show"])
    assert code == 2
    err = capsys.readouterr().err
    assert "config_invalid_http_security" in err
