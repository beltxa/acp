from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse


WELL_KNOWN_PATH = "/.well-known/acp"
DEFAULT_IDENTITY_DOCUMENT_PATH = "/api/v1/acp/identity"


class WellKnownError(ValueError):
    pass


def well_known_url_from_base(base_url: str) -> str:
    normalized = str(base_url or "").strip()
    if not normalized:
        raise WellKnownError("base_url is required")
    if normalized.endswith(WELL_KNOWN_PATH):
        return normalized
    return f"{normalized.rstrip('/')}{WELL_KNOWN_PATH}"


def identity_document_url_from_base(base_url: str) -> str:
    normalized = str(base_url or "").strip()
    if not normalized:
        raise WellKnownError("base_url is required")
    return f"{normalized.rstrip('/')}{DEFAULT_IDENTITY_DOCUMENT_PATH}"


def build_well_known_document(
    *,
    identity_document: dict[str, Any],
    base_url: str,
    identity_document_url: str | None = None,
    version: str = "1.0",
) -> dict[str, Any]:
    agent_id = identity_document.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise WellKnownError("identity_document.agent_id is required")

    service = identity_document.get("service")
    service_map = service if isinstance(service, dict) else {}
    capabilities = identity_document.get("capabilities")
    capabilities_map = capabilities if isinstance(capabilities, dict) else {}

    transports: dict[str, Any] = {}

    direct_endpoint = service_map.get("direct_endpoint")
    if isinstance(direct_endpoint, str) and direct_endpoint.strip():
        http_hint: dict[str, Any] = {"endpoint": direct_endpoint.strip()}
        service_http = service_map.get("http")
        if isinstance(service_http, dict):
            profile = service_http.get("security_profile")
            if isinstance(profile, str) and profile.strip():
                http_hint["security_profile"] = profile.strip()
        transports["http"] = http_hint

    relay_hints = service_map.get("relay_hints")
    if isinstance(relay_hints, list):
        relay_endpoints = [item.strip() for item in relay_hints if isinstance(item, str) and item.strip()]
        if relay_endpoints:
            relay_hint: dict[str, Any] = {"endpoint": relay_endpoints[0]}
            service_relay = service_map.get("relay")
            if isinstance(service_relay, dict):
                profile = service_relay.get("security_profile")
                if isinstance(profile, str) and profile.strip():
                    relay_hint["security_profile"] = profile.strip()
            transports["relay"] = relay_hint
            if len(relay_endpoints) > 1:
                transports["relay"]["hints"] = relay_endpoints

    amqp_service = service_map.get("amqp")
    if isinstance(amqp_service, dict) and amqp_service:
        transports["amqp"] = dict(amqp_service)

    mqtt_service = service_map.get("mqtt")
    if isinstance(mqtt_service, dict) and mqtt_service:
        transports["mqtt"] = dict(mqtt_service)

    security_profile = _security_profile_hint(transports)
    identity_ref = identity_document_url or identity_document_url_from_base(base_url)

    document: dict[str, Any] = {
        "agent_id": agent_id,
        "identity_document": identity_ref,
        "transports": transports,
        "version": version,
        "security_profile": security_profile,
    }
    supports = capabilities_map.get("supports")
    if isinstance(supports, dict):
        document["capabilities"] = sorted([key for key, enabled in supports.items() if enabled])
    return document


def parse_well_known_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WellKnownError("Well-known response must be a JSON object")
    agent_id = value.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise WellKnownError("Well-known response missing agent_id")
    transports = value.get("transports")
    if not isinstance(transports, dict):
        raise WellKnownError("Well-known response missing transports")
    version = value.get("version")
    if not isinstance(version, str) or not version.strip():
        raise WellKnownError("Well-known response missing version")
    identity_reference = value.get("identity_document")
    if not (
        isinstance(identity_reference, str)
        or isinstance(identity_reference, dict)
    ):
        raise WellKnownError("Well-known response missing identity_document reference")
    return dict(value)


def resolve_identity_document_reference(
    well_known: dict[str, Any],
    *,
    source_url: str,
) -> str | dict[str, Any]:
    reference = well_known.get("identity_document")
    if isinstance(reference, dict):
        return reference
    if not isinstance(reference, str) or not reference.strip():
        raise WellKnownError("Well-known response identity_document reference is invalid")
    parsed = urlparse(reference)
    if parsed.scheme and parsed.netloc:
        return reference
    return urljoin(source_url, reference)


def _security_profile_hint(transports: dict[str, Any]) -> str:
    for transport_name in ("http", "relay"):
        hint = transports.get(transport_name)
        if isinstance(hint, dict):
            profile = hint.get("security_profile")
            if isinstance(profile, str) and profile.strip():
                return profile.strip()
    http_hint = transports.get("http")
    if isinstance(http_hint, dict):
        endpoint = http_hint.get("endpoint")
        if isinstance(endpoint, str):
            if endpoint.startswith("https://"):
                return "https"
            if endpoint.startswith("http://"):
                return "http"
    return "https"
