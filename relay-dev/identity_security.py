from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


class IdentityVerificationError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        raise IdentityVerificationError("Invalid base64 data in signature material") from exc


def _verify_ed25519_signature(data: bytes, signature_b64: str, public_key_b64: str) -> bool:
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(_b64decode(public_key_b64))
        public_key.verify(_b64decode(signature_b64), data)
        return True
    except InvalidSignature:
        return False
    except Exception as exc:  # noqa: BLE001
        raise IdentityVerificationError("Invalid signing key material") from exc


def verify_identity_document(
    identity_document: dict[str, Any],
    *,
    expected_agent_id: str | None = None,
) -> None:
    for key in ("agent_id", "keys", "service", "signature", "valid_until"):
        if key not in identity_document:
            raise IdentityVerificationError(f"Identity document missing required field: {key}")

    agent_id = identity_document.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise IdentityVerificationError("Identity document agent_id must be a non-empty string")
    if expected_agent_id is not None and agent_id != expected_agent_id:
        raise IdentityVerificationError(
            f"Identity document agent_id mismatch (expected {expected_agent_id}, got {agent_id})",
        )

    valid_until = identity_document.get("valid_until")
    if not isinstance(valid_until, str):
        raise IdentityVerificationError("Identity document valid_until must be an ISO-8601 string")
    try:
        if datetime.fromisoformat(valid_until.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise IdentityVerificationError("Identity document is expired")
    except IdentityVerificationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IdentityVerificationError("Identity document valid_until is not a valid ISO-8601 timestamp") from exc

    signature = identity_document.get("signature", {})
    if not isinstance(signature, dict):
        raise IdentityVerificationError("Identity document signature must be an object")
    signature_value = signature.get("value")
    if not isinstance(signature_value, str) or not signature_value.strip():
        raise IdentityVerificationError("Identity document signature.value is required")

    signing = identity_document.get("keys", {}).get("signing", {})
    signing_public_key = signing.get("public_key") if isinstance(signing, dict) else None
    if not isinstance(signing_public_key, str) or not signing_public_key.strip():
        raise IdentityVerificationError("Identity document signing public key is required")

    signed_by = signature.get("signed_by")
    signing_kid = signing.get("kid") if isinstance(signing, dict) else None
    if isinstance(signed_by, str) and isinstance(signing_kid, str) and signed_by != signing_kid:
        raise IdentityVerificationError("Identity document signature signed_by does not match signing key kid")

    unsigned_document = dict(identity_document)
    unsigned_document.pop("signature", None)
    payload = canonical_json(unsigned_document).encode("utf-8")
    if not _verify_ed25519_signature(payload, signature_value, signing_public_key):
        raise IdentityVerificationError("Identity document signature verification failed")


def _signable_protected(protected: dict[str, Any]) -> dict[str, Any]:
    wrapped_content_keys = protected.get("wrapped_content_keys")
    if not isinstance(wrapped_content_keys, list):
        raise IdentityVerificationError("protected.wrapped_content_keys must be a list")

    normalized_keys: list[dict[str, Any]] = []
    for item in wrapped_content_keys:
        if not isinstance(item, dict):
            raise IdentityVerificationError("protected.wrapped_content_keys entries must be objects")
        recipient = item.get("recipient")
        if not isinstance(recipient, str) or not recipient.strip():
            raise IdentityVerificationError("protected.wrapped_content_keys[].recipient is required")
        normalized_keys.append(dict(item))

    nonce = protected.get("nonce")
    ciphertext = protected.get("ciphertext")
    payload_hash = protected.get("payload_hash")
    signature_kid = protected.get("signature_kid")
    if not all(isinstance(value, str) and value.strip() for value in (nonce, ciphertext, payload_hash, signature_kid)):
        raise IdentityVerificationError(
            "protected must include non-empty nonce, ciphertext, payload_hash, and signature_kid",
        )

    normalized_keys.sort(key=lambda entry: str(entry.get("recipient", "")))
    return {
        "nonce": nonce,
        "ciphertext": ciphertext,
        "wrapped_content_keys": normalized_keys,
        "payload_hash": payload_hash,
        "signature_kid": signature_kid,
    }


def verify_message_signature(
    message: dict[str, Any],
    *,
    sender_identity_document: dict[str, Any],
) -> None:
    envelope = message.get("envelope")
    protected = message.get("protected")
    if not isinstance(envelope, dict):
        raise IdentityVerificationError("Message envelope must be an object for signature verification")
    if not isinstance(protected, dict):
        raise IdentityVerificationError("Message protected payload must be an object for signature verification")

    sender = envelope.get("sender")
    if not isinstance(sender, str) or not sender.strip():
        raise IdentityVerificationError("Message sender must be a non-empty string")

    verify_identity_document(sender_identity_document, expected_agent_id=sender)

    signature_value = protected.get("signature")
    if not isinstance(signature_value, str) or not signature_value.strip():
        raise IdentityVerificationError("protected.signature is required")

    signing_public_key = (
        sender_identity_document.get("keys", {})
        .get("signing", {})
        .get("public_key")
    )
    if not isinstance(signing_public_key, str) or not signing_public_key.strip():
        raise IdentityVerificationError("Sender signing public key is missing from identity document")

    signing_kid = (
        sender_identity_document.get("keys", {})
        .get("signing", {})
        .get("kid")
    )
    signature_kid = protected.get("signature_kid")
    if isinstance(signing_kid, str) and isinstance(signature_kid, str) and signing_kid != signature_kid:
        raise IdentityVerificationError("protected.signature_kid does not match sender signing key kid")

    body = {
        "envelope": envelope,
        "protected": _signable_protected(protected),
    }
    payload = canonical_json(body).encode("utf-8")
    if not _verify_ed25519_signature(payload, signature_value, signing_public_key):
        raise IdentityVerificationError("Message signature verification failed")
