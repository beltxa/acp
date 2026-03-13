from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any
import uuid

from .crypto import canonical_json, generate_ed25519_keypair, generate_x25519_keypair, sign_bytes, verify_signature


IDENTITY_FILE_NAME = "identity.json"
IDENTITY_DOC_FILE_NAME = "identity_document.json"
_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
TRUST_PROFILES = {
    "self_asserted",
    "domain_verified",
    "enterprise_managed",
    "regulated_assured",
}


class IdentityError(ValueError):
    pass


def parse_agent_id(agent_id: str) -> tuple[str, str | None]:
    match = _AGENT_ID_PATTERN.match(agent_id)
    if match is None:
        raise IdentityError(f"Invalid agent identifier: {agent_id}")
    return match.group("name"), match.group("domain")


def sanitize_agent_id(agent_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", agent_id)


def identity_path(storage_dir: Path, agent_id: str) -> Path:
    return storage_dir / sanitize_agent_id(agent_id)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class AgentIdentity:
    agent_id: str
    signing_private_key: str
    signing_public_key: str
    encryption_private_key: str
    encryption_public_key: str
    signing_kid: str
    encryption_kid: str

    @classmethod
    def create(cls, agent_id: str) -> "AgentIdentity":
        parse_agent_id(agent_id)
        signing_private_key, signing_public_key = generate_ed25519_keypair()
        encryption_private_key, encryption_public_key = generate_x25519_keypair()
        return cls(
            agent_id=agent_id,
            signing_private_key=signing_private_key,
            signing_public_key=signing_public_key,
            encryption_private_key=encryption_private_key,
            encryption_public_key=encryption_public_key,
            signing_kid=f"sig-{uuid.uuid4().hex[:12]}",
            encryption_kid=f"enc-{uuid.uuid4().hex[:12]}",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "agent_id": self.agent_id,
            "signing_private_key": self.signing_private_key,
            "signing_public_key": self.signing_public_key,
            "encryption_private_key": self.encryption_private_key,
            "encryption_public_key": self.encryption_public_key,
            "signing_kid": self.signing_kid,
            "encryption_kid": self.encryption_kid,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AgentIdentity":
        return cls(
            agent_id=str(value["agent_id"]),
            signing_private_key=str(value["signing_private_key"]),
            signing_public_key=str(value["signing_public_key"]),
            encryption_private_key=str(value["encryption_private_key"]),
            encryption_public_key=str(value["encryption_public_key"]),
            signing_kid=str(value["signing_kid"]),
            encryption_kid=str(value["encryption_kid"]),
        )

    def build_identity_document(
        self,
        *,
        direct_endpoint: str | None,
        relay_hints: list[str] | None,
        trust_profile: str,
        capabilities: dict[str, Any] | None = None,
        valid_days: int = 365,
    ) -> dict[str, Any]:
        if trust_profile not in TRUST_PROFILES:
            raise IdentityError(
                f"Unsupported trust_profile {trust_profile}; expected one of {sorted(TRUST_PROFILES)}",
            )
        document = {
            "acp_identity_version": "1.0",
            "agent_id": self.agent_id,
            "created_at": _utc_now_iso(),
            "valid_until": (
                datetime.now(timezone.utc) + timedelta(days=valid_days)
            ).isoformat().replace("+00:00", "Z"),
            "trust_profile": trust_profile,
            "keys": {
                "signing": {
                    "kid": self.signing_kid,
                    "alg": "Ed25519",
                    "public_key": self.signing_public_key,
                },
                "encryption": {
                    "kid": self.encryption_kid,
                    "alg": "X25519",
                    "public_key": self.encryption_public_key,
                },
            },
            "service": {
                "direct_endpoint": direct_endpoint,
                "relay_hints": relay_hints or [],
            },
            "capabilities": capabilities or {},
        }
        to_sign = canonical_json(document).encode("utf-8")
        document["signature"] = {
            "algorithm": "Ed25519",
            "signed_by": self.signing_kid,
            "value": sign_bytes(to_sign, self.signing_private_key),
        }
        return document


def verify_identity_document(identity_document: dict[str, Any]) -> bool:
    required = ["agent_id", "keys", "service", "signature", "valid_until"]
    for key in required:
        if key not in identity_document:
            return False

    signature = identity_document.get("signature", {})
    signature_value = signature.get("value")
    signing_public_key = (
        identity_document.get("keys", {})
        .get("signing", {})
        .get("public_key")
    )
    if not signature_value or not signing_public_key:
        return False

    trust_profile = identity_document.get("trust_profile")
    if trust_profile not in TRUST_PROFILES:
        return False

    valid_until = identity_document.get("valid_until")
    if not isinstance(valid_until, str):
        return False
    try:
        if datetime.fromisoformat(valid_until.replace("Z", "+00:00")) <= datetime.now(
            timezone.utc,
        ):
            return False
    except Exception:  # noqa: BLE001
        return False

    unsigned_document = dict(identity_document)
    unsigned_document.pop("signature", None)
    to_verify = canonical_json(unsigned_document).encode("utf-8")
    return verify_signature(to_verify, signature_value, signing_public_key)


def write_identity(
    storage_dir: Path,
    identity: AgentIdentity,
    identity_document: dict[str, Any],
) -> None:
    agent_dir = identity_path(storage_dir, identity.agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)
    identity_file = agent_dir / IDENTITY_FILE_NAME
    document_file = agent_dir / IDENTITY_DOC_FILE_NAME
    identity_file.write_text(canonical_json(identity.to_dict()), encoding="utf-8")
    document_file.write_text(canonical_json(identity_document), encoding="utf-8")


def read_identity(storage_dir: Path, agent_id: str) -> tuple[AgentIdentity, dict[str, Any]] | None:
    agent_dir = identity_path(storage_dir, agent_id)
    identity_file = agent_dir / IDENTITY_FILE_NAME
    document_file = agent_dir / IDENTITY_DOC_FILE_NAME
    if not identity_file.exists() or not document_file.exists():
        return None

    import json

    identity = AgentIdentity.from_dict(json.loads(identity_file.read_text(encoding="utf-8")))
    identity_document = json.loads(document_file.read_text(encoding="utf-8"))
    return identity, identity_document
