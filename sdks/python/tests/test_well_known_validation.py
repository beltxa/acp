from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from acp.discovery import DiscoveryClient, DiscoveryError
from acp.identity import AgentIdentity
from acp.well_known import parse_well_known_document


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "vectors" / "well_known"


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None, *, json_error: bool = False) -> None:
        self.status_code = status_code
        self._body = body
        self._json_error = json_error

    def json(self) -> dict[str, Any]:
        if self._json_error:
            raise ValueError("Malformed JSON")
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture_name",
    [
        "invalid_missing_agent_id.json",
        "invalid_missing_version.json",
        "invalid_identity_document_type.json",
        "invalid_identity_document_relative_path.json",
        "invalid_identity_document_url.json",
        "invalid_transports_type.json",
        "invalid_transport_hint_shape.json",
        "invalid_transport_endpoint_type.json",
        "invalid_transport_endpoint_url.json",
        "invalid_version.json",
        "invalid_security_profile.json",
    ],
)
def test_parse_well_known_rejects_malformed_fields(fixture_name: str) -> None:
    payload = _load_fixture(fixture_name)
    with pytest.raises(ValueError):
        parse_well_known_document(payload)


def test_parse_well_known_accepts_valid_fixture() -> None:
    payload = _load_fixture("valid_basic.json")
    parsed = parse_well_known_document(payload)
    assert parsed["agent_id"] == "agent:shipping.bot@company.local"
    assert parsed["version"] == "1.0"


def test_malformed_json_fixture_is_invalid_json() -> None:
    raw = (FIXTURES_DIR / "malformed_json.txt").read_text(encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


def test_discovery_rejects_http_well_known_by_default() -> None:
    client = DiscoveryClient()
    with pytest.raises(DiscoveryError):
        client.resolve_well_known("http://company.local")


def test_discovery_accepts_http_well_known_with_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = AgentIdentity.create("agent:inventory.bot@company.local")
    identity_document = target.build_identity_document(
        direct_endpoint="http://company.local/acp/inbox",
        relay_hints=[],
        trust_profile="self_asserted",
        capabilities={"agent_id": target.agent_id},
    )
    well_known = _load_fixture("valid_basic.json")
    well_known["agent_id"] = target.agent_id
    well_known["identity_document"] = "http://company.local/api/v1/acp/identity"
    well_known["transports"]["http"]["endpoint"] = "http://company.local/acp/inbox"
    well_known["security_profile"] = "http"

    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if params is not None:
            return DummyResponse(404)
        if url == "http://company.local/.well-known/acp":
            return DummyResponse(200, well_known)
        if url == "http://company.local/api/v1/acp/identity":
            return DummyResponse(200, {"identity_document": identity_document})
        return DummyResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)
    client = DiscoveryClient(cache_path=tmp_path / "cache.json", allow_insecure_http=True)
    resolved = client.resolve_well_known("http://company.local", expected_agent_id=target.agent_id)
    assert resolved["identity_document"]["agent_id"] == target.agent_id


def test_discovery_handles_empty_or_malformed_well_known_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if url == "https://company.local/.well-known/acp":
            return DummyResponse(200, None, json_error=True)
        return DummyResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)
    client = DiscoveryClient()
    with pytest.raises(DiscoveryError):
        client.resolve_well_known("https://company.local")
