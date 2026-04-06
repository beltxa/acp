# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .messages import Envelope, ProtectedPayload, WrappedContentKey


class CryptoError(RuntimeError):
    pass


def b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def generate_ed25519_keypair() -> tuple[str, str]:
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
    return b64encode(private_bytes), b64encode(public_bytes)


def generate_x25519_keypair() -> tuple[str, str]:
    private_key = x25519.X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return b64encode(private_bytes), b64encode(public_bytes)


def _load_ed25519_private(private_key_b64: str) -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.from_private_bytes(b64decode(private_key_b64))


def _load_ed25519_public(public_key_b64: str) -> ed25519.Ed25519PublicKey:
    return ed25519.Ed25519PublicKey.from_public_bytes(b64decode(public_key_b64))


def _load_x25519_private(private_key_b64: str) -> x25519.X25519PrivateKey:
    return x25519.X25519PrivateKey.from_private_bytes(b64decode(private_key_b64))


def _load_x25519_public(public_key_b64: str) -> x25519.X25519PublicKey:
    return x25519.X25519PublicKey.from_public_bytes(b64decode(public_key_b64))


def sign_bytes(data: bytes, signing_private_key_b64: str) -> str:
    private_key = _load_ed25519_private(signing_private_key_b64)
    return b64encode(private_key.sign(data))


def verify_signature(data: bytes, signature_b64: str, signing_public_key_b64: str) -> bool:
    public_key = _load_ed25519_public(signing_public_key_b64)
    try:
        public_key.verify(b64decode(signature_b64), data)
        return True
    except InvalidSignature:
        return False


def envelope_aad(envelope: Envelope | dict[str, Any]) -> bytes:
    raw = envelope if isinstance(envelope, dict) else envelope.to_dict()
    aad = {
        "acp_version": raw["acp_version"],
        "message_id": raw["message_id"],
        "operation_id": raw["operation_id"],
        "sender": raw["sender"],
        "recipients": raw["recipients"],
    }
    if raw.get("tenant") is not None:
        aad["tenant"] = raw["tenant"]
    return canonical_json(aad).encode("utf-8")


def _derive_wrap_key(shared_secret: bytes, recipient: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"acp-v1-wrap:{recipient}".encode("utf-8"),
    )
    return hkdf.derive(shared_secret)


def encrypt_for_recipients(
    payload: dict[str, Any],
    envelope: Envelope,
    recipient_encryption_public_keys: Mapping[str, str],
) -> ProtectedPayload:
    plaintext = canonical_json(payload).encode("utf-8")
    content_key = os.urandom(32)
    nonce = os.urandom(12)

    payload_aad = envelope_aad(envelope)
    ciphertext = AESGCM(content_key).encrypt(nonce, plaintext, payload_aad)

    ephemeral_private = x25519.X25519PrivateKey.generate()
    ephemeral_public_bytes = ephemeral_private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )

    wrapped_content_keys: list[WrappedContentKey] = []
    for recipient, recipient_public_key_b64 in recipient_encryption_public_keys.items():
        recipient_public = _load_x25519_public(recipient_public_key_b64)
        shared_secret = ephemeral_private.exchange(recipient_public)
        wrap_key = _derive_wrap_key(shared_secret, recipient)
        wrap_nonce = os.urandom(12)
        wrapped_cek = AESGCM(wrap_key).encrypt(
            wrap_nonce,
            content_key,
            envelope.message_id.encode("utf-8"),
        )
        wrapped_content_keys.append(
            WrappedContentKey(
                recipient=recipient,
                ephemeral_public_key=b64encode(ephemeral_public_bytes),
                nonce=b64encode(wrap_nonce),
                ciphertext=b64encode(wrapped_cek),
            )
        )

    return ProtectedPayload(
        nonce=b64encode(nonce),
        ciphertext=b64encode(ciphertext),
        wrapped_content_keys=wrapped_content_keys,
        payload_hash=sha256_hex(ciphertext),
        signature_kid="",
        signature="",
    )


def _message_signature_input(envelope: Envelope, protected: ProtectedPayload) -> bytes:
    body = {
        "envelope": envelope.to_dict(),
        "protected": protected.to_signable_dict(),
    }
    return canonical_json(body).encode("utf-8")


def sign_protected_payload(
    envelope: Envelope,
    protected: ProtectedPayload,
    signing_private_key_b64: str,
    signature_kid: str,
) -> ProtectedPayload:
    protected.signature_kid = signature_kid
    protected.signature = sign_bytes(
        _message_signature_input(envelope, protected),
        signing_private_key_b64,
    )
    return protected


def verify_protected_payload_signature(
    envelope: Envelope,
    protected: ProtectedPayload,
    sender_signing_public_key_b64: str,
) -> bool:
    if not protected.signature:
        return False
    return verify_signature(
        _message_signature_input(envelope, protected),
        protected.signature,
        sender_signing_public_key_b64,
    )


def decrypt_for_recipient(
    envelope: Envelope,
    protected: ProtectedPayload,
    recipient_id: str,
    recipient_encryption_private_key_b64: str,
) -> dict[str, Any]:
    matching = next(
        (item for item in protected.wrapped_content_keys if item.recipient == recipient_id),
        None,
    )
    if matching is None:
        raise CryptoError(f"No wrapped content key available for recipient {recipient_id}")

    recipient_private = _load_x25519_private(recipient_encryption_private_key_b64)
    ephemeral_public = _load_x25519_public(matching.ephemeral_public_key)
    shared_secret = recipient_private.exchange(ephemeral_public)
    wrap_key = _derive_wrap_key(shared_secret, recipient_id)

    try:
        content_key = AESGCM(wrap_key).decrypt(
            b64decode(matching.nonce),
            b64decode(matching.ciphertext),
            envelope.message_id.encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("Failed to unwrap content key") from exc

    try:
        plaintext = AESGCM(content_key).decrypt(
            b64decode(protected.nonce),
            b64decode(protected.ciphertext),
            envelope_aad(envelope),
        )
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("Failed to decrypt message payload") from exc

    return json.loads(plaintext.decode("utf-8"))
