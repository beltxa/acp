from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import warnings
from typing import Any

import requests

from .http_security import (
    HttpSecurityError,
    HttpSecurityPolicy,
    enforce_http_security,
    requests_cert_value,
    requests_verify_value,
    validate_http_security_policy,
)
from .identity import parse_agent_id, verify_identity_document
from .well_known import (
    WellKnownError,
    parse_well_known_document,
    resolve_identity_document_reference,
    well_known_url_from_base,
)


class DiscoveryError(RuntimeError):
    pass


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class CachedDocument:
    identity_document: dict[str, Any]
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_document": self.identity_document,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CachedDocument":
        return cls(
            identity_document=dict(value["identity_document"]),
            fetched_at=str(value["fetched_at"]),
        )


class DiscoveryClient:
    def __init__(
        self,
        *,
        cache_path: Path | None = None,
        default_scheme: str = "https",
        relay_hints: list[str] | None = None,
        enterprise_directory_hints: list[str] | None = None,
        timeout_seconds: int = 5,
        allow_insecure_http: bool = False,
        allow_insecure_tls: bool = False,
        ca_file: str | None = None,
        mtls_enabled: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
    ) -> None:
        self.default_scheme = default_scheme
        self.relay_hints = relay_hints or []
        self.enterprise_directory_hints = enterprise_directory_hints or []
        self.timeout_seconds = timeout_seconds
        self.policy = HttpSecurityPolicy(
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=cert_file,
            key_file=key_file,
        )
        self._warned_messages: set[str] = set()
        try:
            warning_messages = validate_http_security_policy(
                self.policy,
                context="Discovery configuration",
            )
        except HttpSecurityError as exc:
            raise DiscoveryError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        self.cache_path = cache_path
        self.cache: dict[str, CachedDocument] = {}
        if self.cache_path is not None:
            self._load_cache()

    def _emit_warning(self, message: str) -> None:
        if message in self._warned_messages:
            return
        self._warned_messages.add(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _verify_for_url(self, url: str, *, context: str) -> tuple[bool | str, tuple[str, str] | None]:
        try:
            warning_messages = enforce_http_security(url, policy=self.policy, context=context)
        except HttpSecurityError as exc:
            raise DiscoveryError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        try:
            cert = requests_cert_value(url, policy=self.policy)
        except HttpSecurityError as exc:
            raise DiscoveryError(str(exc)) from exc
        return requests_verify_value(url, policy=self.policy), cert

    def _load_cache(self) -> None:
        if self.cache_path is None or not self.cache_path.exists():
            return
        raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        for agent_id, value in raw.items():
            self.cache[agent_id] = CachedDocument.from_dict(value)

    def _persist_cache(self) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {agent_id: cached.to_dict() for agent_id, cached in self.cache.items()}
        self.cache_path.write_text(
            json.dumps(raw, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def seed(self, identity_document: dict[str, Any]) -> None:
        agent_id = identity_document["agent_id"]
        self.cache[agent_id] = CachedDocument(
            identity_document=identity_document,
            fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self._persist_cache()

    def _cache_valid(self, identity_document: dict[str, Any]) -> bool:
        valid_until = identity_document.get("valid_until")
        if not isinstance(valid_until, str):
            return False
        return _parse_iso8601(valid_until) > datetime.now(timezone.utc)

    def _try_cache(self, agent_id: str) -> dict[str, Any] | None:
        cached = self.cache.get(agent_id)
        if cached is None:
            return None
        if self._cache_valid(cached.identity_document):
            return cached.identity_document
        self.cache.pop(agent_id, None)
        self._persist_cache()
        return None

    def _cache_identity(self, agent_id: str, identity_document: dict[str, Any]) -> None:
        self.cache[agent_id] = CachedDocument(
            identity_document=identity_document,
            fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self._persist_cache()

    def _validate(self, identity_document: dict[str, Any]) -> bool:
        if not verify_identity_document(identity_document):
            return False
        return self._cache_valid(identity_document)

    def _well_known_url(self, agent_id: str) -> str:
        _, domain = parse_agent_id(agent_id)
        if domain is None:
            raise DiscoveryError(
                f"Agent {agent_id} does not include a domain, cannot use .well-known discovery",
            )
        return f"{self.default_scheme}://{domain}/.well-known/acp"

    def _request_json(
        self,
        *,
        url: str,
        context: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        verify, cert = self._verify_for_url(url, context=context)
        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout_seconds,
                verify=verify,
                cert=cert,
            )
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def _extract_identity_document(self, body: dict[str, Any]) -> dict[str, Any] | None:
        identity_document = body.get("identity_document")
        if identity_document is None and "agent_id" in body:
            identity_document = body
        return identity_document if isinstance(identity_document, dict) else None

    def _fetch_identity_document_url(
        self,
        *,
        identity_document_url: str,
        context: str,
    ) -> dict[str, Any] | None:
        body = self._request_json(url=identity_document_url, context=context)
        if body is None:
            return None
        return self._extract_identity_document(body)

    def _resolve_well_known(
        self,
        *,
        well_known_url: str,
        expected_agent_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        body = self._request_json(url=well_known_url, context="Discovery .well-known lookup")
        if body is None:
            return None
        try:
            well_known = parse_well_known_document(body)
        except WellKnownError:
            return None
        if expected_agent_id and well_known.get("agent_id") != expected_agent_id:
            return None
        try:
            identity_reference = resolve_identity_document_reference(
                well_known,
                source_url=well_known_url,
            )
        except WellKnownError:
            return None
        if isinstance(identity_reference, dict):
            identity_document = identity_reference
        else:
            identity_document = self._fetch_identity_document_url(
                identity_document_url=identity_reference,
                context="Discovery identity document lookup",
            )
            if identity_document is None:
                return None
        if not self._validate(identity_document):
            return None
        if expected_agent_id and identity_document.get("agent_id") != expected_agent_id:
            return None
        return well_known, identity_document

    def resolve_well_known(
        self,
        base_url: str,
        *,
        expected_agent_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            well_known_url = well_known_url_from_base(base_url)
        except WellKnownError as exc:
            raise DiscoveryError(str(exc)) from exc
        resolved = self._resolve_well_known(
            well_known_url=well_known_url,
            expected_agent_id=expected_agent_id,
        )
        if resolved is None:
            raise DiscoveryError(f"Unable to resolve well-known metadata from {well_known_url}")
        well_known, identity_document = resolved
        self._cache_identity(str(identity_document["agent_id"]), identity_document)
        return {
            "well_known_url": well_known_url,
            "well_known": well_known,
            "identity_document": identity_document,
        }

    def _try_well_known(self, agent_id: str) -> dict[str, Any] | None:
        try:
            url = self._well_known_url(agent_id)
        except DiscoveryError:
            return None
        resolved = self._resolve_well_known(well_known_url=url, expected_agent_id=agent_id)
        if resolved is None:
            return None
        _, identity_document = resolved
        if not self._validate(identity_document):
            return None
        self._cache_identity(agent_id, identity_document)
        return identity_document

    def _try_relays(self, agent_id: str) -> dict[str, Any] | None:
        for relay_hint in self.relay_hints:
            url = f"{relay_hint.rstrip('/')}/discover"
            body = self._request_json(
                url=url,
                params={"agent_id": agent_id},
                context="Discovery relay hint lookup",
            )
            if body is None:
                continue
            identity_document = self._extract_identity_document(body)
            if identity_document is None:
                continue
            if not self._validate(identity_document):
                continue
            self._cache_identity(agent_id, identity_document)
            return identity_document
        return None

    def _try_enterprise_directories(self, agent_id: str) -> dict[str, Any] | None:
        for directory_hint in self.enterprise_directory_hints:
            url = f"{directory_hint.rstrip('/')}/discover"
            body = self._request_json(
                url=url,
                params={"agent_id": agent_id},
                context="Discovery enterprise directory lookup",
            )
            if body is None:
                continue
            identity_document = self._extract_identity_document(body)
            if identity_document is None:
                continue
            if not self._validate(identity_document):
                continue
            self._cache_identity(agent_id, identity_document)
            return identity_document
        return None

    def resolve(self, agent_id: str) -> dict[str, Any]:
        cached = self._try_cache(agent_id)
        if cached is not None:
            return cached

        well_known = self._try_well_known(agent_id)
        if well_known is not None:
            return well_known

        relay_doc = self._try_relays(agent_id)
        if relay_doc is not None:
            return relay_doc

        enterprise_doc = self._try_enterprise_directories(agent_id)
        if enterprise_doc is not None:
            return enterprise_doc

        raise DiscoveryError(f"Unable to resolve identity document for {agent_id}")
