# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from .identity import read_identity, sanitize_agent_id


class KeyProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class IdentityKeyMaterial:
    signing_private_key: str
    encryption_private_key: str
    signing_public_key: str | None = None
    encryption_public_key: str | None = None
    signing_kid: str | None = None
    encryption_kid: str | None = None


@dataclass(frozen=True)
class TlsMaterial:
    cert_file: str | None = None
    key_file: str | None = None
    ca_file: str | None = None


class KeyProvider(Protocol):
    def load_identity_keys(self, agent_id: str) -> IdentityKeyMaterial:
        ...

    def load_tls_material(self, agent_id: str | None = None) -> TlsMaterial:
        ...

    def load_ca_bundle(self, agent_id: str | None = None) -> str | None:
        ...

    def describe(self) -> dict[str, Any]:
        ...


class LocalKeyProvider:
    def __init__(
        self,
        *,
        storage_dir: str | Path,
        cert_file: str | None = None,
        key_file: str | None = None,
        ca_file: str | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.cert_file = cert_file.strip() if isinstance(cert_file, str) and cert_file.strip() else None
        self.key_file = key_file.strip() if isinstance(key_file, str) and key_file.strip() else None
        self.ca_file = ca_file.strip() if isinstance(ca_file, str) and ca_file.strip() else None

    def load_identity_keys(self, agent_id: str) -> IdentityKeyMaterial:
        bundle = read_identity(self.storage_dir, agent_id)
        if bundle is None:
            raise KeyProviderError(f"Local identity not found for {agent_id}")
        identity, _identity_document = bundle
        return IdentityKeyMaterial(
            signing_private_key=identity.signing_private_key,
            encryption_private_key=identity.encryption_private_key,
            signing_public_key=identity.signing_public_key,
            encryption_public_key=identity.encryption_public_key,
            signing_kid=identity.signing_kid,
            encryption_kid=identity.encryption_kid,
        )

    def load_tls_material(self, agent_id: str | None = None) -> TlsMaterial:  # noqa: ARG002
        return TlsMaterial(cert_file=self.cert_file, key_file=self.key_file, ca_file=self.ca_file)

    def load_ca_bundle(self, agent_id: str | None = None) -> str | None:  # noqa: ARG002
        return self.ca_file

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "local",
            "storage_dir": str(self.storage_dir),
        }


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
    ) -> None:
        if not isinstance(vault_url, str) or not vault_url.strip():
            raise KeyProviderError("vault_url is required for VaultKeyProvider")
        if not isinstance(vault_path, str) or not vault_path.strip():
            raise KeyProviderError("vault_path is required for VaultKeyProvider")
        self.vault_url = vault_url.rstrip("/")
        self.vault_path = vault_path.strip().strip("/")
        self.vault_token_env = vault_token_env.strip() if vault_token_env.strip() else "VAULT_TOKEN"
        self._token = token.strip() if isinstance(token, str) and token.strip() else None
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.ca_file = ca_file.strip() if isinstance(ca_file, str) and ca_file.strip() else None
        self.allow_insecure_tls = allow_insecure_tls
        self._cache: dict[str, dict[str, Any]] = {}

    def load_identity_keys(self, agent_id: str) -> IdentityKeyMaterial:
        secret = self._load_secret(agent_id)
        signing_private = _secret_value(
            secret,
            "signing_key",
            "identity_signing_key",
            "signing_private_key",
        )
        encryption_private = _secret_value(
            secret,
            "encryption_key",
            "identity_encryption_key",
            "encryption_private_key",
        )
        if signing_private is None:
            raise KeyProviderError(f"Vault secret for {agent_id} is missing signing_key")
        if encryption_private is None:
            raise KeyProviderError(f"Vault secret for {agent_id} is missing encryption_key")
        return IdentityKeyMaterial(
            signing_private_key=signing_private,
            encryption_private_key=encryption_private,
            signing_public_key=_secret_value(secret, "signing_public_key"),
            encryption_public_key=_secret_value(secret, "encryption_public_key"),
            signing_kid=_secret_value(secret, "signing_kid"),
            encryption_kid=_secret_value(secret, "encryption_kid"),
        )

    def load_tls_material(self, agent_id: str | None = None) -> TlsMaterial:
        secret = self._load_secret(agent_id)
        return TlsMaterial(
            cert_file=_secret_value(secret, "tls_cert_file", "tls_cert", "cert_file"),
            key_file=_secret_value(secret, "tls_key_file", "tls_key", "key_file"),
            ca_file=_secret_value(secret, "ca_bundle_file", "ca_file", "ca_bundle"),
        )

    def load_ca_bundle(self, agent_id: str | None = None) -> str | None:
        secret = self._load_secret(agent_id)
        return _secret_value(secret, "ca_bundle_file", "ca_file", "ca_bundle")

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "vault",
            "vault_url": self.vault_url,
            "vault_path": self.vault_path,
            "vault_token_env": self.vault_token_env,
        }

    def _secret_path(self, agent_id: str | None) -> str:
        if "{agent_id}" in self.vault_path:
            target = sanitize_agent_id(agent_id or "")
            return self.vault_path.format(agent_id=target)
        if agent_id is None:
            return self.vault_path
        return f"{self.vault_path}/{sanitize_agent_id(agent_id)}"

    def _load_secret(self, agent_id: str | None) -> dict[str, Any]:
        secret_path = self._secret_path(agent_id)
        if secret_path in self._cache:
            return self._cache[secret_path]

        token = self._resolve_token()
        if token is None:
            raise KeyProviderError(
                f"Vault token is missing. Set token or environment variable {self.vault_token_env}.",
            )
        url = f"{self.vault_url}/v1/{secret_path.lstrip('/')}"
        verify: bool | str = False if self.allow_insecure_tls else (self.ca_file or True)
        headers = {"X-Vault-Token": token}
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                verify=verify,
            )
        except requests.RequestException as exc:
            raise KeyProviderError(f"Vault request failed for path {secret_path}: {exc}") from exc
        if response.status_code != 200:
            raise KeyProviderError(
                f"Vault returned HTTP {response.status_code} for path {secret_path}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise KeyProviderError(f"Vault returned non-JSON response for path {secret_path}") from exc
        if not isinstance(payload, dict):
            raise KeyProviderError(f"Vault response for path {secret_path} must be a JSON object")
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            # Vault KV v2 shape.
            data = data.get("data")
        if not isinstance(data, dict):
            raise KeyProviderError(f"Vault response for path {secret_path} is missing data object")
        self._cache[secret_path] = data
        return data

    def _resolve_token(self) -> str | None:
        if self._token:
            return self._token
        import os

        env_value = os.getenv(self.vault_token_env)
        if not isinstance(env_value, str) or not env_value.strip():
            return None
        return env_value.strip()


def _secret_value(secret: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        raw = secret.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None
