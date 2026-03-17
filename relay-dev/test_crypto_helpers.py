from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from identity_security import canonical_json


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _generate_ed25519_keypair() -> tuple[str, str]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return _b64encode(private_bytes), _b64encode(public_bytes)


def _generate_x25519_public_key() -> str:
    private_key = x25519.X25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return _b64encode(public_bytes)


def _sign_bytes(data: bytes, signing_private_key_b64: str) -> str:
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(_b64decode(signing_private_key_b64))
    return _b64encode(private_key.sign(data))


def _signable_protected(protected: dict[str, Any]) -> dict[str, Any]:
    keys = protected.get("wrapped_content_keys", [])
    normalized = [dict(item) for item in keys if isinstance(item, dict)]
    normalized.sort(key=lambda item: str(item.get("recipient", "")))
    return {
        "nonce": str(protected.get("nonce", "")),
        "ciphertext": str(protected.get("ciphertext", "")),
        "wrapped_content_keys": normalized,
        "payload_hash": str(protected.get("payload_hash", "")),
        "signature_kid": str(protected.get("signature_kid", "")),
    }


def build_signed_identity_document(
    agent_id: str,
    *,
    direct_endpoint: str | None,
    amqp: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    signing_private_key, signing_public_key = _generate_ed25519_keypair()
    encryption_public_key = _generate_x25519_public_key()
    signing_kid = f"sig-{agent_id.replace(':', '-').replace('@', '-')}"
    encryption_kid = f"enc-{agent_id.replace(':', '-').replace('@', '-')}"

    service: dict[str, Any] = {
        "relay_hints": [],
    }
    if direct_endpoint is not None:
        service["direct_endpoint"] = direct_endpoint
    if amqp is not None:
        service["amqp"] = dict(amqp)

    identity_document: dict[str, Any] = {
        "agent_id": agent_id,
        "valid_until": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat().replace("+00:00", "Z"),
        "trust_profile": "internal",
        "keys": {
            "signing": {
                "kid": signing_kid,
                "alg": "Ed25519",
                "public_key": signing_public_key,
            },
            "encryption": {
                "kid": encryption_kid,
                "alg": "X25519",
                "public_key": encryption_public_key,
            },
        },
        "service": service,
        "capabilities": {},
    }
    signature = _sign_bytes(canonical_json(identity_document).encode("utf-8"), signing_private_key)
    identity_document["signature"] = {
        "algorithm": "Ed25519",
        "signed_by": signing_kid,
        "value": signature,
    }
    return identity_document, signing_private_key


def attach_signed_sender(
    message: dict[str, Any],
    *,
    sender_identity_document: dict[str, Any],
    sender_signing_private_key: str,
) -> dict[str, Any]:
    protected = dict(message.get("protected", {}))
    protected["nonce"] = str(protected.get("nonce", "bm9uY2U="))
    protected["ciphertext"] = str(protected.get("ciphertext", "Y2lwaGVydGV4dA=="))
    protected["wrapped_content_keys"] = (
        protected.get("wrapped_content_keys")
        if isinstance(protected.get("wrapped_content_keys"), list)
        else []
    )
    protected["payload_hash"] = str(protected.get("payload_hash", "deadbeef"))

    signing_kid = (
        sender_identity_document.get("keys", {})
        .get("signing", {})
        .get("kid")
    )
    protected["signature_kid"] = str(signing_kid or "sig-unknown")

    signable = {
        "envelope": message["envelope"],
        "protected": _signable_protected(protected),
    }
    protected["signature"] = _sign_bytes(
        canonical_json(signable).encode("utf-8"),
        sender_signing_private_key,
    )

    message["protected"] = protected
    message["sender_identity_document"] = sender_identity_document
    return message
