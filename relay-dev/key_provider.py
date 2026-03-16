from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any, Protocol

import requests


class KeyProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TlsMaterial:
    cert_file: str | None = None
    key_file: str | None = None
    ca_file: str | None = None


class RelayKeyProvider(Protocol):
    def load_tls_material(self, target_id: str | None = None) -> TlsMaterial:
        ...

    def load_ca_bundle(self, target_id: str | None = None) -> str | None:
        ...

    def describe(self) -> dict[str, Any]:
        ...


class LocalKeyProvider:
    def __init__(
        self,
        *,
        cert_file: str | None = None,
        key_file: str | None = None,
        ca_file: str | None = None,
    ) -> None:
        self.cert_file = _normalize_optional(cert_file)
        self.key_file = _normalize_optional(key_file)
        self.ca_file = _normalize_optional(ca_file)

    def load_tls_material(self, target_id: str | None = None) -> TlsMaterial:  # noqa: ARG002
        return TlsMaterial(cert_file=self.cert_file, key_file=self.key_file, ca_file=self.ca_file)

    def load_ca_bundle(self, target_id: str | None = None) -> str | None:  # noqa: ARG002
        return self.ca_file

    def describe(self) -> dict[str, Any]:
        return {"provider": "local"}


class VaultKeyProvider:
    def __init__(
        self,
        *,
        vault_url: str,
        vault_path: str,
        vault_token_env: str = "VAULT_TOKEN",
        token: str | None = None,
        timeout_seconds: int = 5,
        ca_file: str | None = None,
        allow_insecure_tls: bool = False,
        allow_insecure_http: bool = False,
    ) -> None:
        self.vault_url = _required(vault_url, "vault_url").rstrip("/")
        self.vault_path = _required(vault_path, "vault_path").strip().strip("/")
        self.vault_token_env = _normalize_optional(vault_token_env) or "VAULT_TOKEN"
        self._token = _normalize_optional(token)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.ca_file = _normalize_optional(ca_file)
        self.allow_insecure_tls = bool(allow_insecure_tls)
        self.allow_insecure_http = bool(allow_insecure_http)
        self._cache: dict[str, dict[str, Any]] = {}

        if self.vault_url.lower().startswith("http://") and not self.allow_insecure_http:
            raise KeyProviderError(
                "vault_url uses insecure HTTP but ACP_ALLOW_INSECURE_HTTP is not enabled.",
            )

    def load_tls_material(self, target_id: str | None = None) -> TlsMaterial:
        secret = self._load_secret(target_id)
        return TlsMaterial(
            cert_file=_secret_value(secret, "tls_cert_file", "tls_cert", "cert_file"),
            key_file=_secret_value(secret, "tls_key_file", "tls_key", "key_file"),
            ca_file=_secret_value(secret, "ca_bundle_file", "ca_file", "ca_bundle"),
        )

    def load_ca_bundle(self, target_id: str | None = None) -> str | None:
        secret = self._load_secret(target_id)
        return _secret_value(secret, "ca_bundle_file", "ca_file", "ca_bundle")

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "vault",
            "vault_url": self.vault_url,
            "vault_path": self.vault_path,
            "vault_token_env": self.vault_token_env,
        }

    def _secret_path(self, target_id: str | None) -> str:
        if "{agent_id}" in self.vault_path:
            return self.vault_path.format(agent_id=_sanitize_agent_id(target_id or "relay"))
        if target_id is None:
            return self.vault_path
        return f"{self.vault_path}/{_sanitize_agent_id(target_id)}"

    def _load_secret(self, target_id: str | None) -> dict[str, Any]:
        path = self._secret_path(target_id)
        if path in self._cache:
            return self._cache[path]

        token = self._resolve_token()
        if token is None:
            raise KeyProviderError(
                f"Vault token is missing. Set token or environment variable {self.vault_token_env}.",
            )

        url = f"{self.vault_url}/v1/{path.lstrip('/')}"
        verify: bool | str = False if self.allow_insecure_tls else (self.ca_file or True)
        try:
            response = requests.get(
                url,
                headers={"X-Vault-Token": token},
                timeout=self.timeout_seconds,
                verify=verify,
            )
        except requests.RequestException as exc:
            raise KeyProviderError(f"Vault request failed for path {path}: {exc}") from exc
        if response.status_code != 200:
            raise KeyProviderError(f"Vault returned HTTP {response.status_code} for path {path}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise KeyProviderError(f"Vault returned non-JSON response for path {path}") from exc
        if not isinstance(payload, dict):
            raise KeyProviderError(f"Vault response for path {path} must be a JSON object")
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data.get("data")
        if not isinstance(data, dict):
            raise KeyProviderError(f"Vault response for path {path} is missing data object")
        self._cache[path] = data
        return data

    def _resolve_token(self) -> str | None:
        if self._token:
            return self._token
        value = os.getenv(self.vault_token_env)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()


def _required(value: str | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KeyProviderError(f"{label} is required")
    return value.strip()


def _normalize_optional(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _secret_value(secret: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = secret.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sanitize_agent_id(agent_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in agent_id)


def resolve_key_provider(
    *,
    key_provider: str,
    vault_url: str | None,
    vault_path: str | None,
    vault_token_env: str,
    vault_token: str | None,
    timeout_seconds: int,
    ca_file: str | None,
    allow_insecure_tls: bool,
    allow_insecure_http: bool,
    cert_file: str | None,
    key_file: str | None,
) -> RelayKeyProvider:
    normalized = (key_provider or "local").strip().lower() or "local"
    if normalized == "local":
        return LocalKeyProvider(cert_file=cert_file, key_file=key_file, ca_file=ca_file)
    if normalized == "vault":
        return VaultKeyProvider(
            vault_url=_required(vault_url, "vault_url"),
            vault_path=_required(vault_path, "vault_path"),
            vault_token_env=vault_token_env,
            token=vault_token,
            timeout_seconds=timeout_seconds,
            ca_file=ca_file,
            allow_insecure_tls=allow_insecure_tls,
            allow_insecure_http=allow_insecure_http,
        )
    raise KeyProviderError(f"Unsupported key provider: {normalized}")
