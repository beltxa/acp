from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from acp.agent import Agent
from acp.identity import AgentIdentity, read_identity, write_identity
from acp.key_provider import IdentityKeyMaterial, KeyProviderError, LocalKeyProvider, TlsMaterial, VaultKeyProvider
from acp.transport import TransportError


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def _seed_identity(storage_dir: Path, agent_id: str) -> AgentIdentity:
    identity = AgentIdentity.create(agent_id)
    document = identity.build_identity_document(
        direct_endpoint=None,
        relay_hints=[],
        trust_profile="self_asserted",
        capabilities={"agent_id": agent_id},
    )
    write_identity(storage_dir, identity, document)
    return identity


def test_local_key_provider_parity_with_existing_identity(tmp_path: Path) -> None:
    agent_id = "agent:key.local@demo"
    identity = _seed_identity(tmp_path, agent_id)
    provider = LocalKeyProvider(
        storage_dir=tmp_path,
        cert_file="/tmp/client-cert.pem",
        key_file="/tmp/client-key.pem",
        ca_file="/tmp/ca.pem",
    )

    keys = provider.load_identity_keys(agent_id)
    tls = provider.load_tls_material(agent_id)

    assert keys.signing_private_key == identity.signing_private_key
    assert keys.encryption_private_key == identity.encryption_private_key
    assert keys.signing_public_key == identity.signing_public_key
    assert keys.encryption_public_key == identity.encryption_public_key
    assert keys.signing_kid == identity.signing_kid
    assert keys.encryption_kid == identity.encryption_kid
    assert tls == TlsMaterial(
        cert_file="/tmp/client-cert.pem",
        key_file="/tmp/client-key.pem",
        ca_file="/tmp/ca.pem",
    )
    assert provider.load_ca_bundle(agent_id) == "/tmp/ca.pem"
    assert provider.describe()["provider"] == "local"


def test_local_key_provider_missing_identity_raises(tmp_path: Path) -> None:
    provider = LocalKeyProvider(storage_dir=tmp_path)
    with pytest.raises(KeyProviderError, match="Local identity not found"):
        provider.load_identity_keys("agent:missing@demo")


def test_vault_key_provider_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, *, headers: dict[str, str], timeout: int, verify: bool | str) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["verify"] = verify
        return _FakeResponse(
            200,
            {
                "data": {
                    "data": {
                        "signing_key": "sig-private",
                        "encryption_key": "enc-private",
                        "signing_public_key": "sig-public",
                        "encryption_public_key": "enc-public",
                        "signing_kid": "sig-kid",
                        "encryption_kid": "enc-kid",
                        "tls_cert_file": "/etc/acp/client-cert.pem",
                        "tls_key_file": "/etc/acp/client-key.pem",
                        "ca_file": "/etc/acp/ca.pem",
                    },
                },
            },
        )

    monkeypatch.setenv("VAULT_TOKEN", "token-123")
    monkeypatch.setattr("acp.key_provider.requests.get", fake_get)

    provider = VaultKeyProvider(
        vault_url="https://vault.local",
        vault_path="secret/data/acp/identities",
        vault_token_env="VAULT_TOKEN",
        timeout_seconds=7,
    )
    keys = provider.load_identity_keys("agent:john.chess@demo")
    tls = provider.load_tls_material("agent:john.chess@demo")

    assert captured["url"] == "https://vault.local/v1/secret/data/acp/identities/agent_john.chess_demo"
    assert captured["headers"]["X-Vault-Token"] == "token-123"
    assert captured["timeout"] == 7
    assert captured["verify"] is True
    assert keys == IdentityKeyMaterial(
        signing_private_key="sig-private",
        encryption_private_key="enc-private",
        signing_public_key="sig-public",
        encryption_public_key="enc-public",
        signing_kid="sig-kid",
        encryption_kid="enc-kid",
    )
    assert tls == TlsMaterial(
        cert_file="/etc/acp/client-cert.pem",
        key_file="/etc/acp/client-key.pem",
        ca_file="/etc/acp/ca.pem",
    )
    assert provider.load_ca_bundle("agent:john.chess@demo") == "/etc/acp/ca.pem"


def test_vault_key_provider_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    provider = VaultKeyProvider(
        vault_url="https://vault.local",
        vault_path="secret/data/acp/identities",
    )
    with pytest.raises(KeyProviderError, match="Vault token is missing"):
        provider.load_identity_keys("agent:john@demo")


def test_vault_key_provider_missing_required_fields_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(_url: str, *, headers: dict[str, str], timeout: int, verify: bool | str) -> _FakeResponse:
        _ = headers, timeout, verify
        return _FakeResponse(200, {"data": {"data": {"encryption_key": "enc-only"}}})

    monkeypatch.setenv("VAULT_TOKEN", "token-123")
    monkeypatch.setattr("acp.key_provider.requests.get", fake_get)
    provider = VaultKeyProvider(
        vault_url="https://vault.local",
        vault_path="secret/data/acp/identities",
    )
    with pytest.raises(KeyProviderError, match="missing signing_key"):
        provider.load_identity_keys("agent:john@demo")


def test_agent_load_or_create_uses_custom_key_provider(tmp_path: Path) -> None:
    bootstrap_identity = AgentIdentity.create("agent:provider.bootstrap@demo")

    class FakeProvider:
        def load_identity_keys(self, agent_id: str) -> IdentityKeyMaterial:
            assert agent_id == "agent:provider.bootstrap@demo"
            return IdentityKeyMaterial(
                signing_private_key=bootstrap_identity.signing_private_key,
                encryption_private_key=bootstrap_identity.encryption_private_key,
                signing_public_key=bootstrap_identity.signing_public_key,
                encryption_public_key=bootstrap_identity.encryption_public_key,
                signing_kid=bootstrap_identity.signing_kid,
                encryption_kid=bootstrap_identity.encryption_kid,
            )

        def load_tls_material(self, agent_id: str | None = None) -> TlsMaterial:
            _ = agent_id
            return TlsMaterial()

        def load_ca_bundle(self, agent_id: str | None = None) -> str | None:
            _ = agent_id
            return None

        def describe(self) -> dict[str, Any]:
            return {"provider": "fake", "path": "secret/acp/identities"}

    agent = Agent.load_or_create(
        "agent:provider.bootstrap@demo",
        storage_dir=tmp_path / "agent",
        key_provider=FakeProvider(),
        relay_url="https://relay.example",
    )
    assert agent.key_provider_info["provider"] == "fake"
    assert agent.identity.signing_private_key == bootstrap_identity.signing_private_key
    assert agent.identity.encryption_private_key == bootstrap_identity.encryption_private_key
    assert read_identity(tmp_path / "agent", "agent:provider.bootstrap@demo") is not None


def test_agent_load_or_create_external_provider_requires_public_metadata(tmp_path: Path) -> None:
    local_identity = AgentIdentity.create("agent:provider.incomplete@demo")

    class IncompleteProvider:
        def load_identity_keys(self, _agent_id: str) -> IdentityKeyMaterial:
            return IdentityKeyMaterial(
                signing_private_key=local_identity.signing_private_key,
                encryption_private_key=local_identity.encryption_private_key,
            )

        def load_tls_material(self, agent_id: str | None = None) -> TlsMaterial:
            _ = agent_id
            return TlsMaterial()

        def load_ca_bundle(self, agent_id: str | None = None) -> str | None:
            _ = agent_id
            return None

        def describe(self) -> dict[str, Any]:
            return {"provider": "incomplete"}

    with pytest.raises(TransportError, match="first-time bootstrap"):
        Agent.load_or_create(
            "agent:provider.incomplete@demo",
            storage_dir=tmp_path / "agent",
            key_provider=IncompleteProvider(),
            relay_url="https://relay.example",
        )
