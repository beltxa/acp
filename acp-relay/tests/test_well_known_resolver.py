from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routing import RelayDiscoveryResolver, RelayRoutingConfig  # noqa: E402


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


def _identity_document(agent_id: str, endpoint: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "valid_until": "2099-01-01T00:00:00Z",
        "keys": {
            "signing": {"public_key": "sig-key"},
            "encryption": {"public_key": "enc-key"},
        },
        "service": {
            "direct_endpoint": endpoint,
            "relay_hints": [],
        },
    }


def test_resolver_fetches_identity_via_well_known_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    recipient_id = "agent:shipping.bot@company.local"
    identity_document = _identity_document(recipient_id, "https://company.local/acp/inbox")
    well_known = {
        "agent_id": recipient_id,
        "identity_document": "https://company.local/api/v1/acp/identity",
        "transports": {"http": {"endpoint": "https://company.local/acp/inbox"}},
        "version": "1.0",
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

    resolver = RelayDiscoveryResolver(
        RelayRoutingConfig(
            default_scheme="https",
            timeout_seconds=1,
        ),
    )
    resolved = resolver.resolve(recipient_id)
    assert resolved["agent_id"] == recipient_id
    assert resolved["service"]["direct_endpoint"] == "https://company.local/acp/inbox"
