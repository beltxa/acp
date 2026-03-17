# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from .identity import IdentityError, parse_agent_id


WELL_KNOWN_PATH = "/.well-known/acp"
DEFAULT_IDENTITY_DOCUMENT_PATH = "/api/v1/acp/identity"
SUPPORTED_WELL_KNOWN_VERSION = "1.0"
SUPPORTED_SECURITY_PROFILES = {"http", "https", "mtls", "https+mtls"}


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
    version: str = SUPPORTED_WELL_KNOWN_VERSION,
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
    if version != SUPPORTED_WELL_KNOWN_VERSION:
        raise WellKnownError(
            f"Unsupported well-known version {version}; expected {SUPPORTED_WELL_KNOWN_VERSION}",
        )
    identity_ref = identity_document_url or identity_document_url_from_base(base_url)
    _validate_identity_document_reference(identity_ref)

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
    try:
        parse_agent_id(agent_id)
    except IdentityError as exc:
        raise WellKnownError(f"Well-known response has invalid agent_id: {agent_id}") from exc
    transports = value.get("transports")
    if not isinstance(transports, dict):
        raise WellKnownError("Well-known response missing transports")
    version = value.get("version")
    if version != SUPPORTED_WELL_KNOWN_VERSION:
        raise WellKnownError(
            f"Well-known response version must be {SUPPORTED_WELL_KNOWN_VERSION}",
        )
    identity_reference = value.get("identity_document")
    if not isinstance(identity_reference, str):
        raise WellKnownError("Well-known response identity_document must be a URL string")
    _validate_identity_document_reference(identity_reference)
    _validate_transports(transports)
    security_profile = value.get("security_profile")
    if security_profile is not None:
        if not isinstance(security_profile, str) or security_profile not in SUPPORTED_SECURITY_PROFILES:
            raise WellKnownError(
                "Well-known response security_profile is invalid",
            )
    return dict(value)


def resolve_identity_document_reference(
    well_known: dict[str, Any],
    *,
    source_url: str,
) -> str:
    reference = well_known.get("identity_document")
    if not isinstance(reference, str) or not reference.strip():
        raise WellKnownError("Well-known response identity_document reference is invalid")
    _validate_identity_document_reference(reference)
    parsed = urlparse(reference)
    if parsed.scheme and parsed.netloc:
        return reference
    return urljoin(source_url, reference)


def _validate_identity_document_reference(reference: str) -> None:
    parsed = urlparse(reference)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise WellKnownError("identity_document URL must use http or https")
        if not parsed.netloc:
            raise WellKnownError("identity_document URL is missing host")
        return
    if not reference.startswith("/"):
        raise WellKnownError("identity_document URL must be absolute http(s) or root-relative path")


def _validate_transports(transports: dict[str, Any]) -> None:
    for transport_name, hint in transports.items():
        if not isinstance(hint, dict):
            raise WellKnownError(f"Well-known transport hint {transport_name} must be an object")
        endpoint = hint.get("endpoint")
        if endpoint is not None and not isinstance(endpoint, str):
            raise WellKnownError(f"Well-known transport hint {transport_name}.endpoint must be a string")
        if isinstance(endpoint, str):
            parsed = urlparse(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise WellKnownError(
                    f"Well-known transport hint {transport_name}.endpoint must be an absolute http(s) URL",
                )
        security_profile = hint.get("security_profile")
        if security_profile is not None:
            if not isinstance(security_profile, str) or security_profile not in SUPPORTED_SECURITY_PROFILES:
                raise WellKnownError(
                    f"Well-known transport hint {transport_name}.security_profile is invalid",
                )


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
