from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from key_provider import KeyProviderError, resolve_key_provider  # noqa: E402
from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_resolve_local_provider_material(tmp_path: Path) -> None:
    cert_file = tmp_path / "cert.pem"
    key_file = tmp_path / "key.pem"
    ca_file = tmp_path / "ca.pem"
    cert_file.write_text("cert", encoding="utf-8")
    key_file.write_text("key", encoding="utf-8")
    ca_file.write_text("ca", encoding="utf-8")

    provider = resolve_key_provider(
        key_provider="local",
        vault_url=None,
        vault_path=None,
        vault_token_env="VAULT_TOKEN",
        vault_token=None,
        timeout_seconds=5,
        ca_file=str(ca_file),
        allow_insecure_tls=False,
        allow_insecure_http=False,
        cert_file=str(cert_file),
        key_file=str(key_file),
    )
    material = provider.load_tls_material("relay")
    assert material.ca_file == str(ca_file)
    assert material.cert_file == str(cert_file)
    assert material.key_file == str(key_file)
    assert provider.describe()["provider"] == "local"


def test_resolve_vault_provider_material(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
        verify: bool | str,
    ) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["verify"] = verify
        return _FakeResponse(
            200,
            {
                "data": {
                    "data": {
                        "tls_cert_file": "/etc/acp/relay-cert.pem",
                        "tls_key_file": "/etc/acp/relay-key.pem",
                        "ca_file": "/etc/acp/ca.pem",
                    },
                },
            },
        )

    monkeypatch.setenv("VAULT_TOKEN", "token-123")
    monkeypatch.setattr("key_provider.requests.get", fake_get)
    provider = resolve_key_provider(
        key_provider="vault",
        vault_url="https://vault.example",
        vault_path="secret/data/acp/relay",
        vault_token_env="VAULT_TOKEN",
        vault_token=None,
        timeout_seconds=7,
        ca_file=None,
        allow_insecure_tls=False,
        allow_insecure_http=False,
        cert_file=None,
        key_file=None,
    )
    material = provider.load_tls_material("relay")
    assert material.ca_file == "/etc/acp/ca.pem"
    assert material.cert_file == "/etc/acp/relay-cert.pem"
    assert material.key_file == "/etc/acp/relay-key.pem"
    assert captured["url"] == "https://vault.example/v1/secret/data/acp/relay/relay"
    assert captured["headers"]["X-Vault-Token"] == "token-123"


def test_router_snapshot_exposes_key_provider_metadata(tmp_path: Path) -> None:
    cert_file = tmp_path / "cert.pem"
    key_file = tmp_path / "key.pem"
    ca_file = tmp_path / "ca.pem"
    cert_file.write_text("cert", encoding="utf-8")
    key_file.write_text("key", encoding="utf-8")
    ca_file.write_text("ca", encoding="utf-8")

    config = RelayRoutingConfig(
        allow_insecure_http=False,
        allow_insecure_tls=False,
        mtls_enabled=True,
        cert_file=str(cert_file),
        key_file=str(key_file),
        ca_file=str(ca_file),
        key_provider_info={"provider": "local"},
    )
    resolver = RelayDiscoveryResolver(config)
    router = RelayRouter(
        resolver,
        allow_insecure_http=False,
        allow_insecure_tls=False,
        mtls_enabled=True,
        cert_file=str(cert_file),
        key_file=str(key_file),
        ca_file=str(ca_file),
    )
    snapshot = router.routing_snapshot()
    key_provider = snapshot["http_security"]["key_provider"]
    assert key_provider["provider"] == "local"
    assert snapshot["http_security"]["mtls_enabled"] is True


def test_vault_provider_missing_path_fails() -> None:
    with pytest.raises(KeyProviderError):
        resolve_key_provider(
            key_provider="vault",
            vault_url="https://vault.example",
            vault_path=None,
            vault_token_env="VAULT_TOKEN",
            vault_token=None,
            timeout_seconds=5,
            ca_file=None,
            allow_insecure_tls=False,
            allow_insecure_http=False,
            cert_file=None,
            key_file=None,
        )
