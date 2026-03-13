from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

import requests

from .identity import parse_agent_id, verify_identity_document


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
    ) -> None:
        self.default_scheme = default_scheme
        self.relay_hints = relay_hints or []
        self.enterprise_directory_hints = enterprise_directory_hints or []
        self.timeout_seconds = timeout_seconds
        self.cache_path = cache_path
        self.cache: dict[str, CachedDocument] = {}
        if self.cache_path is not None:
            self._load_cache()

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
        agent_name, domain = parse_agent_id(agent_id)
        if domain is None:
            raise DiscoveryError(
                f"Agent {agent_id} does not include a domain, cannot use .well-known discovery",
            )
        return f"{self.default_scheme}://{domain}/.well-known/acp/agents/{agent_name}"

    def _try_well_known(self, agent_id: str) -> dict[str, Any] | None:
        try:
            url = self._well_known_url(agent_id)
        except DiscoveryError:
            return None
        try:
            response = requests.get(url, timeout=self.timeout_seconds)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            identity_document = response.json()
        except ValueError:
            return None
        if not self._validate(identity_document):
            return None
        self._cache_identity(agent_id, identity_document)
        return identity_document

    def _try_relays(self, agent_id: str) -> dict[str, Any] | None:
        for relay_hint in self.relay_hints:
            url = f"{relay_hint.rstrip('/')}/discover"
            try:
                response = requests.get(
                    url,
                    params={"agent_id": agent_id},
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException:
                continue
            if response.status_code != 200:
                continue
            try:
                body = response.json()
            except ValueError:
                continue
            identity_document = body.get("identity_document") if isinstance(body, dict) else None
            if identity_document is None and isinstance(body, dict) and "agent_id" in body:
                identity_document = body
            if not isinstance(identity_document, dict):
                continue
            if not self._validate(identity_document):
                continue
            self._cache_identity(agent_id, identity_document)
            return identity_document
        return None

    def _try_enterprise_directories(self, agent_id: str) -> dict[str, Any] | None:
        for directory_hint in self.enterprise_directory_hints:
            url = f"{directory_hint.rstrip('/')}/discover"
            try:
                response = requests.get(
                    url,
                    params={"agent_id": agent_id},
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException:
                continue
            if response.status_code != 200:
                continue
            try:
                body = response.json()
            except ValueError:
                continue
            identity_document = body.get("identity_document") if isinstance(body, dict) else None
            if identity_document is None and isinstance(body, dict) and "agent_id" in body:
                identity_document = body
            if not isinstance(identity_document, dict):
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
