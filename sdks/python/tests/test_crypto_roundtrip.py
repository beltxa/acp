from acp.crypto import decrypt_for_recipient, encrypt_for_recipients, sign_protected_payload, verify_protected_payload_signature
from acp.identity import AgentIdentity
from acp.messages import Envelope, MessageClass


def test_encrypt_sign_verify_decrypt_roundtrip() -> None:
    sender = AgentIdentity.create("agent:sender@localhost:9101")
    recipient = AgentIdentity.create("agent:recipient@localhost:9102")

    envelope = Envelope.build(
        sender=sender.agent_id,
        recipients=[recipient.agent_id],
        message_class=MessageClass.SEND,
        context_id="ctx-1",
        expires_in_seconds=60,
    )
    payload = {"type": "hello", "data": {"value": 42}}

    protected = encrypt_for_recipients(
        payload,
        envelope,
        {recipient.agent_id: recipient.encryption_public_key},
    )
    protected = sign_protected_payload(
        envelope,
        protected,
        sender.signing_private_key,
        sender.signing_kid,
    )

    assert verify_protected_payload_signature(
        envelope,
        protected,
        sender.signing_public_key,
    )
    decrypted = decrypt_for_recipient(
        envelope,
        protected,
        recipient.agent_id,
        recipient.encryption_private_key,
    )
    assert decrypted == payload
