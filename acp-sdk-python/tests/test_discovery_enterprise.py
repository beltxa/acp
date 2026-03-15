from __future__ import annotations

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


def test_discovery_uses_enterprise_directory_after_relay_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_identity = AgentIdentity.create("agent:shipping.bot@company.local")
    target_doc = target_identity.build_identity_document(
        direct_endpoint="https://company.local/acp/inbox",
        relay_hints=["https://relay.company.local"],
        trust_profile="domain_verified",
        capabilities={"agent_id": target_identity.agent_id},
    )

    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if url.startswith("https://company.local/.well-known/acp/agents/"):
            return DummyResponse(404)
        if url == "http://enterprise-directory.local/discover":
            assert params == {"agent_id": target_identity.agent_id}
            return DummyResponse(200, {"identity_document": target_doc})
        return DummyResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)
    client = DiscoveryClient(
        default_scheme="https",
        relay_hints=["http://relay.local"],
        enterprise_directory_hints=["http://enterprise-directory.local"],
        timeout_seconds=5,
        allow_insecure_http=True,
    )

    resolved = client.resolve(target_identity.agent_id)
    assert resolved["agent_id"] == target_identity.agent_id
