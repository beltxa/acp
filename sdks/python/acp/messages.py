# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import uuid
from typing import Any


ACP_VERSION = "1.0"
DEFAULT_CRYPTO_SUITE = "ACP-AES256-GCM+X25519+ED25519"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MessageClass(str, Enum):
    SEND = "SEND"
    ACK = "ACK"
    FAIL = "FAIL"
    CAPABILITIES = "CAPABILITIES"
    COMPENSATE = "COMPENSATE"


class DeliveryState(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


class FailReason(str, Enum):
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    UNSUPPORTED_CRYPTO_SUITE = "UNSUPPORTED_CRYPTO_SUITE"
    UNSUPPORTED_MESSAGE_CLASS = "UNSUPPORTED_MESSAGE_CLASS"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_MESSAGE = "EXPIRED_MESSAGE"
    POLICY_REJECTED = "POLICY_REJECTED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_PROFILE = "UNSUPPORTED_PROFILE"


@dataclass
class WrappedContentKey:
    recipient: str
    ephemeral_public_key: str
    nonce: str
    ciphertext: str

    def to_dict(self) -> dict[str, str]:
        return {
            "recipient": self.recipient,
            "ephemeral_public_key": self.ephemeral_public_key,
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WrappedContentKey":
        return cls(
            recipient=str(value["recipient"]),
            ephemeral_public_key=str(value["ephemeral_public_key"]),
            nonce=str(value["nonce"]),
            ciphertext=str(value["ciphertext"]),
        )


@dataclass
class Envelope:
    acp_version: str
    message_class: MessageClass
    message_id: str
    operation_id: str
    timestamp: str
    expires_at: str
    sender: str
    recipients: list[str]
    context_id: str
    crypto_suite: str = DEFAULT_CRYPTO_SUITE
    correlation_id: str | None = None
    in_reply_to: str | None = None

    @classmethod
    def build(
        cls,
        *,
        sender: str,
        recipients: list[str],
        message_class: MessageClass,
        context_id: str,
        expires_in_seconds: int = 300,
        operation_id: str | None = None,
        correlation_id: str | None = None,
        in_reply_to: str | None = None,
        crypto_suite: str = DEFAULT_CRYPTO_SUITE,
    ) -> "Envelope":
        now = datetime.now(timezone.utc)
        operation = operation_id or str(uuid.uuid4())
        return cls(
            acp_version=ACP_VERSION,
            message_class=message_class,
            message_id=str(uuid.uuid4()),
            operation_id=operation,
            timestamp=now.isoformat().replace("+00:00", "Z"),
            expires_at=(now + timedelta(seconds=expires_in_seconds))
            .isoformat()
            .replace("+00:00", "Z"),
            sender=sender,
            recipients=recipients,
            context_id=context_id,
            crypto_suite=crypto_suite,
            correlation_id=correlation_id,
            in_reply_to=in_reply_to,
        )

    def validate(self) -> None:
        if not self.recipients:
            raise ValueError("Envelope recipients must not be empty")
        if not self.sender:
            raise ValueError("Envelope sender is required")
        if parse_iso8601(self.expires_at) <= parse_iso8601(self.timestamp):
            raise ValueError("Envelope expires_at must be after timestamp")

    def is_expired(self) -> bool:
        return parse_iso8601(self.expires_at) <= datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value: dict[str, Any] = {
            "acp_version": self.acp_version,
            "message_class": self.message_class.value,
            "message_id": self.message_id,
            "operation_id": self.operation_id,
            "timestamp": self.timestamp,
            "expires_at": self.expires_at,
            "sender": self.sender,
            "recipients": self.recipients,
            "context_id": self.context_id,
            "crypto_suite": self.crypto_suite,
        }
        if self.correlation_id is not None:
            value["correlation_id"] = self.correlation_id
        if self.in_reply_to is not None:
            value["in_reply_to"] = self.in_reply_to
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Envelope":
        envelope = cls(
            acp_version=str(value["acp_version"]),
            message_class=MessageClass(value["message_class"]),
            message_id=str(value["message_id"]),
            operation_id=str(value["operation_id"]),
            timestamp=str(value["timestamp"]),
            expires_at=str(value["expires_at"]),
            sender=str(value["sender"]),
            recipients=[str(item) for item in value["recipients"]],
            context_id=str(value["context_id"]),
            crypto_suite=str(value["crypto_suite"]),
            correlation_id=(
                str(value["correlation_id"])
                if value.get("correlation_id") is not None
                else None
            ),
            in_reply_to=(
                str(value["in_reply_to"])
                if value.get("in_reply_to") is not None
                else None
            ),
        )
        envelope.validate()
        return envelope


@dataclass
class ProtectedPayload:
    nonce: str
    ciphertext: str
    wrapped_content_keys: list[WrappedContentKey]
    payload_hash: str
    signature_kid: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
            "wrapped_content_keys": [item.to_dict() for item in self.wrapped_content_keys],
            "payload_hash": self.payload_hash,
            "signature_kid": self.signature_kid,
            "signature": self.signature,
        }

    def to_signable_dict(self) -> dict[str, Any]:
        keys = sorted(
            (item.to_dict() for item in self.wrapped_content_keys),
            key=lambda item: item["recipient"],
        )
        return {
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
            "wrapped_content_keys": keys,
            "payload_hash": self.payload_hash,
            "signature_kid": self.signature_kid,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProtectedPayload":
        return cls(
            nonce=str(value["nonce"]),
            ciphertext=str(value["ciphertext"]),
            wrapped_content_keys=[
                WrappedContentKey.from_dict(item) for item in value["wrapped_content_keys"]
            ],
            payload_hash=str(value["payload_hash"]),
            signature_kid=str(value["signature_kid"]),
            signature=str(value["signature"]),
        )


@dataclass
class ACPMessage:
    envelope: Envelope
    protected: ProtectedPayload
    sender_identity_document: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "envelope": self.envelope.to_dict(),
            "protected": self.protected.to_dict(),
        }
        if self.sender_identity_document is not None:
            value["sender_identity_document"] = self.sender_identity_document
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ACPMessage":
        return cls(
            envelope=Envelope.from_dict(value["envelope"]),
            protected=ProtectedPayload.from_dict(value["protected"]),
            sender_identity_document=value.get("sender_identity_document"),
        )

    @classmethod
    def from_json(cls, value: str) -> "ACPMessage":
        return cls.from_dict(json.loads(value))


@dataclass
class DeliveryOutcome:
    recipient: str
    state: DeliveryState
    status_code: int | None = None
    response_class: MessageClass | None = None
    reason_code: str | None = None
    detail: str | None = None
    response_message: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "recipient": self.recipient,
            "state": self.state.value,
        }
        if self.status_code is not None:
            value["status_code"] = self.status_code
        if self.response_class is not None:
            value["response_class"] = self.response_class.value
        if self.reason_code is not None:
            value["reason_code"] = self.reason_code
        if self.detail is not None:
            value["detail"] = self.detail
        if self.response_message is not None:
            value["response_message"] = self.response_message
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DeliveryOutcome":
        response_class = value.get("response_class")
        return cls(
            recipient=str(value["recipient"]),
            state=DeliveryState(str(value["state"])),
            status_code=value.get("status_code"),
            response_class=MessageClass(response_class) if response_class else None,
            reason_code=value.get("reason_code"),
            detail=value.get("detail"),
            response_message=value.get("response_message"),
        )


@dataclass
class SendResult:
    operation_id: str
    message_id: str
    outcomes: list[DeliveryOutcome]
    message_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "operation_id": self.operation_id,
            "message_id": self.message_id,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }
        if self.message_ids:
            value["message_ids"] = self.message_ids
        return value


@dataclass
class CompensateInstruction:
    operation_id: str
    reason: str
    actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "reason": self.reason,
            "actions": self.actions,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CompensateInstruction":
        return cls(
            operation_id=str(value["operation_id"]),
            reason=str(value["reason"]),
            actions=[dict(item) for item in value.get("actions", [])],
        )


def build_ack_payload(received_message_id: str, status: str = "accepted") -> dict[str, Any]:
    return {
        "status": status,
        "received_message_id": received_message_id,
    }


def build_fail_payload(
    reason_code: str,
    detail: str,
    retriable: bool = False,
) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "detail": detail,
        "retriable": retriable,
    }
