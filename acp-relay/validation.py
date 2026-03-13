from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


REQUIRED_ENVELOPE_FIELDS = {
    "acp_version",
    "message_class",
    "message_id",
    "operation_id",
    "timestamp",
    "expires_at",
    "sender",
    "recipients",
    "context_id",
    "crypto_suite",
}

SUPPORTED_MESSAGE_CLASSES = {"SEND", "ACK", "FAIL", "CAPABILITIES", "COMPENSATE"}


def parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_expired(expires_at: str) -> bool:
    return parse_iso8601(expires_at) <= datetime.now(timezone.utc)


def validate_envelope(envelope: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in envelope:
            errors.append(f"Missing envelope field: {field}")

    if errors:
        return errors

    message_class = envelope.get("message_class")
    if message_class not in SUPPORTED_MESSAGE_CLASSES:
        errors.append(f"Unsupported message_class: {message_class}")

    recipients = envelope.get("recipients")
    if not isinstance(recipients, list) or not recipients:
        errors.append("Envelope recipients must be a non-empty list")
    elif not all(isinstance(item, str) and item for item in recipients):
        errors.append("Envelope recipients must contain non-empty strings")

    try:
        timestamp = parse_iso8601(str(envelope.get("timestamp")))
        expires_at = parse_iso8601(str(envelope.get("expires_at")))
        if expires_at <= timestamp:
            errors.append("Envelope expires_at must be after timestamp")
    except Exception:  # noqa: BLE001
        errors.append("Envelope timestamp/expires_at must be valid ISO-8601 values")

    sender = envelope.get("sender")
    if not isinstance(sender, str) or not sender:
        errors.append("Envelope sender must be a non-empty string")

    return errors
