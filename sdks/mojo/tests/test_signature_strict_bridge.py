# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import copy
from pathlib import Path
import uuid

from acp.crypto import canonical_json, sign_bytes
from acp.messages import MessageClass
from python_bridge import load_or_create_agent, receive


def _agent_options(storage_dir: Path) -> dict[str, str]:
    return {"storage_dir": str(storage_dir)}


def _legacy_null_optional_signature(message: object, signing_private_key: str) -> str:
    envelope = dict(message.envelope.to_dict())
    envelope["correlation_id"] = None
    envelope["in_reply_to"] = None
    signature_input = canonical_json(
        {
            "envelope": envelope,
            "protected": message.protected.to_signable_dict(),
        },
    ).encode("utf-8")
    return sign_bytes(signature_input, signing_private_key)


def test_bridge_rejects_legacy_null_optional_signature(tmp_path: Path) -> None:
    sender = load_or_create_agent(
        "agent:mojo.sig.sender@localhost:9081",
        _agent_options(tmp_path / "sender"),
    )
    recipient = load_or_create_agent(
        "agent:mojo.sig.recipient@localhost:9082",
        _agent_options(tmp_path / "recipient"),
    )

    outbound = sender._build_message(
        recipients=[recipient.agent_id],
        payload={"type": "ping", "message": "hello"},
        recipient_public_keys={
            recipient.agent_id: recipient.identity_document["keys"]["encryption"]["public_key"],
        },
        message_class=MessageClass.SEND,
        context_id="sig-interop",
        operation_id=str(uuid.uuid4()),
        expires_in_seconds=300,
        correlation_id=None,
        in_reply_to=None,
    )
    canonical_message = outbound.to_dict()
    canonical_message["sender_identity_document"] = sender.identity_document

    legacy_signed_message = copy.deepcopy(canonical_message)
    legacy_signed_message["protected"]["signature"] = _legacy_null_optional_signature(
        outbound,
        sender.identity.signing_private_key,
    )

    legacy_result = receive(recipient, legacy_signed_message, None)
    assert legacy_result["state"] == "FAILED"
    assert legacy_result["reason_code"] == "INVALID_SIGNATURE"

    canonical_result = receive(recipient, canonical_message, None)
    assert canonical_result["state"] == "ACKNOWLEDGED"
