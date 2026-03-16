from acp.identity import AgentIdentity, verify_identity_document
import pytest


def test_identity_document_signature_verification() -> None:
    identity = AgentIdentity.create("agent:inventory.bot@localhost:9100")
    document = identity.build_identity_document(
        direct_endpoint="http://localhost:9100/acp/inbox",
        relay_hints=["http://localhost:8080"],
        trust_profile="domain_verified",
        capabilities={"agent_id": identity.agent_id},
    )
    assert verify_identity_document(document)

    tampered = dict(document)
    tampered["trust_profile"] = "self_asserted"
    assert not verify_identity_document(tampered)


def test_identity_document_rejects_unknown_trust_profile() -> None:
    identity = AgentIdentity.create("agent:inventory.bot@localhost:9100")
    with pytest.raises(ValueError):
        identity.build_identity_document(
            direct_endpoint="http://localhost:9100/acp/inbox",
            relay_hints=["http://localhost:8080"],
            trust_profile="unknown_profile",
            capabilities={"agent_id": identity.agent_id},
        )
