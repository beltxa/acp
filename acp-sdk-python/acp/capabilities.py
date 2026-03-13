from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .messages import DEFAULT_CRYPTO_SUITE


def _valid_until_iso(days: int = 365) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace(
        "+00:00",
        "Z",
    )


@dataclass
class AgentCapabilities:
    agent_id: str
    protocol_versions: list[str] = field(default_factory=lambda: ["1.0"])
    crypto_suites: list[str] = field(default_factory=lambda: [DEFAULT_CRYPTO_SUITE])
    transports: list[str] = field(default_factory=lambda: ["https", "http", "relay"])
    supports: dict[str, bool] = field(
        default_factory=lambda: {
            "ack": True,
            "fail": True,
            "compensate": True,
            "direct_delivery": True,
            "relay_delivery": True,
        }
    )
    limits: dict[str, int] = field(default_factory=lambda: {"max_payload_bytes": 1048576})
    profiles: list[str] = field(default_factory=lambda: ["core", "self_asserted"])
    valid_until: str = field(default_factory=_valid_until_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "protocol_versions": self.protocol_versions,
            "crypto_suites": self.crypto_suites,
            "transports": self.transports,
            "supports": self.supports,
            "limits": self.limits,
            "profiles": self.profiles,
            "valid_until": self.valid_until,
        }

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any] | None,
        fallback_agent_id: str,
    ) -> "AgentCapabilities":
        if value is None:
            return cls(agent_id=fallback_agent_id)
        return cls(
            agent_id=str(value.get("agent_id", fallback_agent_id)),
            protocol_versions=[str(item) for item in value.get("protocol_versions", ["1.0"])],
            crypto_suites=[str(item) for item in value.get("crypto_suites", [DEFAULT_CRYPTO_SUITE])],
            transports=[str(item) for item in value.get("transports", ["https", "http", "relay"])],
            supports={str(k): bool(v) for k, v in value.get("supports", {}).items()},
            limits={str(k): int(v) for k, v in value.get("limits", {}).items()},
            profiles=[str(item) for item in value.get("profiles", ["core"])],
            valid_until=str(value.get("valid_until", _valid_until_iso())),
        )


@dataclass
class CapabilityMatch:
    is_compatible: bool
    protocol_version: str | None
    crypto_suite: str | None
    transport: str | None
    reason: str | None = None


def _first_intersection(local: list[str], remote: list[str]) -> str | None:
    for item in local:
        if item in remote:
            return item
    return None


def choose_compatible(
    local: AgentCapabilities,
    remote: AgentCapabilities,
) -> CapabilityMatch:
    protocol_version = _first_intersection(local.protocol_versions, remote.protocol_versions)
    if protocol_version is None:
        return CapabilityMatch(
            is_compatible=False,
            protocol_version=None,
            crypto_suite=None,
            transport=None,
            reason="No compatible protocol version",
        )

    crypto_suite = _first_intersection(local.crypto_suites, remote.crypto_suites)
    if crypto_suite is None:
        return CapabilityMatch(
            is_compatible=False,
            protocol_version=protocol_version,
            crypto_suite=None,
            transport=None,
            reason="No compatible crypto suite",
        )

    transport = _first_intersection(local.transports, remote.transports)
    if transport is None:
        return CapabilityMatch(
            is_compatible=False,
            protocol_version=protocol_version,
            crypto_suite=crypto_suite,
            transport=None,
            reason="No compatible transport",
        )

    return CapabilityMatch(
        is_compatible=True,
        protocol_version=protocol_version,
        crypto_suite=crypto_suite,
        transport=transport,
    )
