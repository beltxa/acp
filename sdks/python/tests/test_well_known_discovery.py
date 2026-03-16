from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from acp.discovery import DiscoveryClient
from acp.identity import AgentIdentity


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


def test_discovery_resolves_identity_document_from_well_known(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = AgentIdentity.create("agent:shipping.bot@company.local")
    identity_document = target.build_identity_document(
        direct_endpoint="https://company.local/acp/inbox",
        relay_hints=["https://relay.company.local"],
        trust_profile="domain_verified",
        capabilities={"agent_id": target.agent_id},
    )
    well_known = {
        "agent_id": target.agent_id,
        "identity_document": "https://company.local/api/v1/acp/identity",
        "transports": {"http": {"endpoint": "https://company.local/acp/inbox"}},
        "version": "1.0",
        "security_profile": "https",
    }

    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if params is not None:
            return DummyResponse(404)
        if url == "https://company.local/.well-known/acp":
            return DummyResponse(200, well_known)
        if url == "https://company.local/api/v1/acp/identity":
            return DummyResponse(200, {"identity_document": identity_document})
        return DummyResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)

    cache_path = tmp_path / "discovery_cache.json"
    client = DiscoveryClient(cache_path=cache_path)
    resolved = client.resolve(target.agent_id)
    assert resolved["agent_id"] == target.agent_id
    assert client.cache[target.agent_id].identity_document["agent_id"] == target.agent_id


def test_resolve_well_known_supports_base_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = AgentIdentity.create("agent:trading.bot@company.local")
    identity_document = target.build_identity_document(
        direct_endpoint="https://company.local/acp/inbox",
        relay_hints=[],
        trust_profile="domain_verified",
        capabilities={"agent_id": target.agent_id},
    )
    well_known = {
        "agent_id": target.agent_id,
        "identity_document": "/api/v1/acp/identity",
        "transports": {"http": {"endpoint": "https://company.local/acp/inbox"}},
        "version": "1.0",
        "security_profile": "https",
    }

    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if params is not None:
            return DummyResponse(404)
        if url == "https://company.local/.well-known/acp":
            return DummyResponse(200, well_known)
        if url == "https://company.local/api/v1/acp/identity":
            return DummyResponse(200, {"identity_document": identity_document})
        return DummyResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)

    client = DiscoveryClient(cache_path=tmp_path / "cache.json")
    resolved = client.resolve_well_known("https://company.local", expected_agent_id=target.agent_id)
    assert resolved["well_known_url"] == "https://company.local/.well-known/acp"
    assert resolved["well_known"]["agent_id"] == target.agent_id
    assert resolved["identity_document"]["agent_id"] == target.agent_id
