from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from http_security import RelayHttpSecurityPolicy, validate_http_security_policy  # noqa: E402
from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig  # noqa: E402
from test_crypto_helpers import attach_signed_sender, build_signed_identity_document  # noqa: E402


def _identity_document(agent_id: str, endpoint: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "valid_until": "2099-01-01T00:00:00Z",
        "keys": {
            "signing": {"public_key": "sig-key"},
            "encryption": {"public_key": "enc-key"},
        },
        "service": {
            "direct_endpoint": endpoint,
            "relay_hints": [],
        },
    }


def _write_mtls_material(tmp_path: Path) -> tuple[str, str, str]:
    ca_file = tmp_path / "ca.pem"
    cert_file = tmp_path / "client-cert.pem"
    key_file = tmp_path / "client-key.pem"
    ca_file.write_text("ca", encoding="utf-8")
    cert_file.write_text("cert", encoding="utf-8")
    key_file.write_text("key", encoding="utf-8")
    return str(ca_file), str(cert_file), str(key_file)


def test_relay_policy_rejects_mtls_without_certificate_material() -> None:
    policy = RelayHttpSecurityPolicy(mtls_enabled=True)
    with pytest.raises(Exception):
        validate_http_security_policy(policy, context="relay policy")


def test_relay_policy_accepts_server_certificate_pair_without_mtls(tmp_path: Path) -> None:
    _, cert_file, key_file = _write_mtls_material(tmp_path)
    policy = RelayHttpSecurityPolicy(
        mtls_enabled=False,
        cert_file=cert_file,
        key_file=key_file,
    )
    warnings = validate_http_security_policy(policy, context="relay policy")
    assert warnings


def test_relay_router_uses_mtls_client_certificate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ca_file, cert_file, key_file = _write_mtls_material(tmp_path)
    recipient_id = "agent:shipping.bot@localhost:9501"
    resolver = RelayDiscoveryResolver(
        RelayRoutingConfig(
            default_scheme="https",
            timeout_seconds=1,
            mtls_enabled=True,
            ca_file=ca_file,
            cert_file=cert_file,
            key_file=key_file,
        ),
    )
    resolver.register_identity_document(
        _identity_document(recipient_id, "https://localhost:9501/acp/inbox"),
    )
    router = RelayRouter(
        resolver,
        timeout_seconds=1,
        store_and_forward=False,
        mtls_enabled=True,
        ca_file=ca_file,
        cert_file=cert_file,
        key_file=key_file,
    )

    observed: dict[str, Any] = {}

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {"state": "ACKNOWLEDGED", "response_message": {"envelope": {"message_class": "ACK"}}}

    def fake_post(
        url: str,
        json: dict[str, Any],
        timeout: int,
        verify: bool | str = True,
        cert: tuple[str, str] | None = None,
    ) -> DummyResponse:
        observed["url"] = url
        observed["verify"] = verify
        observed["cert"] = cert
        return DummyResponse()

    monkeypatch.setattr("routing.requests.post", fake_post)

    sender_id = "agent:inventory.bot@localhost:9500"
    sender_identity_document, sender_signing_private_key = build_signed_identity_document(
        sender_id,
        direct_endpoint="https://localhost:9500/acp/inbox",
    )

    message = {
        "envelope": {
            "acp_version": "1.0",
            "message_class": "SEND",
            "message_id": "m-1",
            "operation_id": "op-1",
            "timestamp": "2026-03-13T10:00:00Z",
            "expires_at": "2026-03-13T10:10:00Z",
            "sender": sender_id,
            "recipients": [recipient_id],
            "context_id": "ctx-1",
            "crypto_suite": "ACP-AES256-GCM+X25519+ED25519",
        },
        "protected": {},
    }
    attach_signed_sender(
        message,
        sender_identity_document=sender_identity_document,
        sender_signing_private_key=sender_signing_private_key,
    )
    outcomes = router.route_message(message)
    assert outcomes[0]["state"] == "ACKNOWLEDGED"
    assert observed["verify"] == ca_file
    assert observed["cert"] == (cert_file, key_file)
