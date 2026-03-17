# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import os
from typing import Any

from acp.discovery import DiscoveryClient
from acp.http_security import (
    HttpSecurityError,
    HttpSecurityPolicy,
    security_profile,
    security_state,
    to_bool,
    validate_http_security_policy,
)
from acp.identity import sanitize_agent_id
from acp.key_provider import KeyProvider, KeyProviderError, LocalKeyProvider, VaultKeyProvider
from acp.transport import HTTPTransport


DEFAULT_CONFIG_PATH = Path.home() / ".acp" / "config.json"


@dataclass
class CliConfig:
    storage_dir: Path = Path(".acp-data")
    discovery_scheme: str = "https"
    relay_hints: list[str] = field(default_factory=list)
    enterprise_directory_hints: list[str] = field(default_factory=list)
    timeout_seconds: int = 5
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    ca_file: str | None = None
    mtls_enabled: bool = False
    cert_file: str | None = None
    key_file: str | None = None
    key_provider: str = "local"
    vault_url: str | None = None
    vault_path: str | None = None
    vault_token_env: str = "VAULT_TOKEN"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CliConfig":
        return cls(
            storage_dir=Path(str(value.get("storage_dir", ".acp-data"))).expanduser(),
            discovery_scheme=str(value.get("discovery_scheme", "https")),
            relay_hints=[str(item) for item in value.get("relay_hints", [])],
            enterprise_directory_hints=[
                str(item) for item in value.get("enterprise_directory_hints", [])
            ],
            timeout_seconds=int(value.get("timeout_seconds", 5)),
            allow_insecure_http=to_bool(value.get("allow_insecure_http"), default=False),
            allow_insecure_tls=to_bool(value.get("allow_insecure_tls"), default=False),
            ca_file=(
                str(value.get("ca_file")).strip()
                if value.get("ca_file") is not None and str(value.get("ca_file")).strip()
                else None
            ),
            mtls_enabled=to_bool(value.get("mtls_enabled"), default=False),
            cert_file=(
                str(value.get("cert_file")).strip()
                if value.get("cert_file") is not None and str(value.get("cert_file")).strip()
                else None
            ),
            key_file=(
                str(value.get("key_file")).strip()
                if value.get("key_file") is not None and str(value.get("key_file")).strip()
                else None
            ),
            key_provider=str(value.get("key_provider", "local")).strip().lower() or "local",
            vault_url=(
                str(value.get("vault_url")).strip()
                if value.get("vault_url") is not None and str(value.get("vault_url")).strip()
                else None
            ),
            vault_path=(
                str(value.get("vault_path")).strip()
                if value.get("vault_path") is not None and str(value.get("vault_path")).strip()
                else None
            ),
            vault_token_env=str(value.get("vault_token_env", "VAULT_TOKEN")).strip() or "VAULT_TOKEN",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "storage_dir": str(self.storage_dir),
            "discovery_scheme": self.discovery_scheme,
            "relay_hints": self.relay_hints,
            "enterprise_directory_hints": self.enterprise_directory_hints,
            "timeout_seconds": self.timeout_seconds,
            "allow_insecure_http": self.allow_insecure_http,
            "allow_insecure_tls": self.allow_insecure_tls,
            "ca_file": self.ca_file,
            "mtls_enabled": self.mtls_enabled,
            "cert_file": self.cert_file,
            "key_file": self.key_file,
            "key_provider": self.key_provider,
            "vault_url": self.vault_url,
            "vault_path": self.vault_path,
            "vault_token_env": self.vault_token_env,
        }


@dataclass
class CliContext:
    config: CliConfig
    json_output: bool
    config_path: Path | None


@dataclass
class CliUserError(RuntimeError):
    message: str
    code: str = "cli_error"
    details: dict[str, Any] | None = None
    exit_code: int = 2


def load_cli_config(
    config_path_arg: str | None,
    storage_dir_override: str | None,
    *,
    allow_insecure_http_override: bool | None = None,
    allow_insecure_tls_override: bool | None = None,
    mtls_enabled_override: bool | None = None,
    ca_file_override: str | None = None,
    cert_file_override: str | None = None,
    key_file_override: str | None = None,
    key_provider_override: str | None = None,
    vault_url_override: str | None = None,
    vault_path_override: str | None = None,
    vault_token_env_override: str | None = None,
) -> tuple[CliConfig, Path | None]:
    raw_config: dict[str, Any] = {}
    selected_path: Path | None = None

    config_path_value = config_path_arg or os.getenv("ACP_CONFIG_FILE")
    if config_path_value is not None and config_path_value.strip():
        selected_path = Path(config_path_value).expanduser()
    elif DEFAULT_CONFIG_PATH.exists():
        selected_path = DEFAULT_CONFIG_PATH

    if selected_path is not None and selected_path.exists():
        try:
            raw_config = json.loads(selected_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CliUserError(
                message=f"Unable to parse config file {selected_path}: {exc}",
                code="config_parse_error",
                exit_code=2,
            ) from exc

    config = CliConfig.from_dict(raw_config)
    if storage_dir_override is not None and storage_dir_override.strip():
        config.storage_dir = Path(storage_dir_override).expanduser()
    env_allow_insecure_http = os.getenv("ACP_ALLOW_INSECURE_HTTP")
    env_allow_insecure_tls = os.getenv("ACP_ALLOW_INSECURE_TLS")
    env_mtls_enabled = os.getenv("ACP_MTLS_ENABLED")
    env_ca_file = os.getenv("ACP_CA_FILE")
    env_cert_file = os.getenv("ACP_CERT_FILE")
    env_key_file = os.getenv("ACP_KEY_FILE")
    env_key_provider = os.getenv("ACP_KEY_PROVIDER")
    env_vault_url = os.getenv("ACP_VAULT_URL")
    env_vault_path = os.getenv("ACP_VAULT_PATH")
    env_vault_token_env = os.getenv("ACP_VAULT_TOKEN_ENV")
    if env_allow_insecure_http is not None:
        config.allow_insecure_http = to_bool(env_allow_insecure_http, default=config.allow_insecure_http)
    if env_allow_insecure_tls is not None:
        config.allow_insecure_tls = to_bool(env_allow_insecure_tls, default=config.allow_insecure_tls)
    if env_mtls_enabled is not None:
        config.mtls_enabled = to_bool(env_mtls_enabled, default=config.mtls_enabled)
    if env_ca_file is not None and env_ca_file.strip():
        config.ca_file = env_ca_file.strip()
    if env_cert_file is not None and env_cert_file.strip():
        config.cert_file = env_cert_file.strip()
    if env_key_file is not None and env_key_file.strip():
        config.key_file = env_key_file.strip()
    if env_key_provider is not None and env_key_provider.strip():
        config.key_provider = env_key_provider.strip().lower()
    if env_vault_url is not None and env_vault_url.strip():
        config.vault_url = env_vault_url.strip()
    if env_vault_path is not None and env_vault_path.strip():
        config.vault_path = env_vault_path.strip()
    if env_vault_token_env is not None and env_vault_token_env.strip():
        config.vault_token_env = env_vault_token_env.strip()
    if allow_insecure_http_override is not None:
        config.allow_insecure_http = allow_insecure_http_override
    if allow_insecure_tls_override is not None:
        config.allow_insecure_tls = allow_insecure_tls_override
    if mtls_enabled_override is not None:
        config.mtls_enabled = mtls_enabled_override
    if ca_file_override is not None and ca_file_override.strip():
        config.ca_file = ca_file_override.strip()
    if cert_file_override is not None and cert_file_override.strip():
        config.cert_file = cert_file_override.strip()
    if key_file_override is not None and key_file_override.strip():
        config.key_file = key_file_override.strip()
    if key_provider_override is not None and key_provider_override.strip():
        config.key_provider = key_provider_override.strip().lower()
    if vault_url_override is not None and vault_url_override.strip():
        config.vault_url = vault_url_override.strip()
    if vault_path_override is not None and vault_path_override.strip():
        config.vault_path = vault_path_override.strip()
    if vault_token_env_override is not None and vault_token_env_override.strip():
        config.vault_token_env = vault_token_env_override.strip()
    config.storage_dir.mkdir(parents=True, exist_ok=True)
    if config.key_provider not in {"local", "vault"}:
        raise CliUserError(
            message=f"Unsupported key_provider: {config.key_provider}",
            code="config_invalid_key_provider",
            exit_code=2,
        )
    if config.key_provider == "vault":
        if not config.vault_url:
            raise CliUserError(
                message="vault_url is required when key_provider=vault",
                code="config_invalid_key_provider",
                exit_code=2,
            )
        if not config.vault_path:
            raise CliUserError(
                message="vault_path is required when key_provider=vault",
                code="config_invalid_key_provider",
                exit_code=2,
            )
    if config.key_provider == "vault" and config.mtls_enabled:
        has_cert = isinstance(config.cert_file, str) and bool(config.cert_file.strip())
        has_key = isinstance(config.key_file, str) and bool(config.key_file.strip())
        if has_cert != has_key:
            raise CliUserError(
                message=(
                    "Invalid HTTP security configuration: when key_provider=vault and mtls_enabled=true, "
                    "configure both cert_file and key_file or leave both unset for provider-backed mTLS material."
                ),
                code="config_invalid_http_security",
                exit_code=2,
            )
    policy = validation_http_security_policy(config)
    try:
        validate_http_security_policy(policy, context="CLI configuration")
    except HttpSecurityError as exc:
        raise CliUserError(
            message=f"Invalid HTTP security configuration: {exc}",
            code="config_invalid_http_security",
            exit_code=2,
        ) from exc
    return config, selected_path


def identity_storage_dir(ctx: CliContext, out_dir: str | None) -> Path:
    if out_dir is None or not out_dir.strip():
        path = ctx.config.storage_dir
    else:
        path = Path(out_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_discovery_client(
    ctx: CliContext,
    *,
    relay_hints_override: list[str] | None = None,
    scheme_override: str | None = None,
) -> DiscoveryClient:
    relay_hints = relay_hints_override if relay_hints_override else ctx.config.relay_hints
    scheme = scheme_override if scheme_override else ctx.config.discovery_scheme
    return DiscoveryClient(
        cache_path=ctx.config.storage_dir / "discovery_cache.json",
        default_scheme=scheme,
        relay_hints=relay_hints,
        enterprise_directory_hints=ctx.config.enterprise_directory_hints,
        timeout_seconds=ctx.config.timeout_seconds,
        allow_insecure_http=ctx.config.allow_insecure_http,
        allow_insecure_tls=ctx.config.allow_insecure_tls,
        ca_file=ctx.config.ca_file,
        mtls_enabled=ctx.config.mtls_enabled,
        cert_file=ctx.config.cert_file,
        key_file=ctx.config.key_file,
    )


def build_http_transport(ctx: CliContext, *, timeout_seconds: int | None = None) -> HTTPTransport:
    return HTTPTransport(
        timeout_seconds=timeout_seconds or max(1, ctx.config.timeout_seconds),
        allow_insecure_http=ctx.config.allow_insecure_http,
        allow_insecure_tls=ctx.config.allow_insecure_tls,
        ca_file=ctx.config.ca_file,
        mtls_enabled=ctx.config.mtls_enabled,
        cert_file=ctx.config.cert_file,
        key_file=ctx.config.key_file,
    )


def build_key_provider(ctx: CliContext, *, storage_dir: Path | None = None) -> KeyProvider:
    if ctx.config.key_provider == "local":
        return LocalKeyProvider(
            storage_dir=storage_dir or ctx.config.storage_dir,
            cert_file=ctx.config.cert_file,
            key_file=ctx.config.key_file,
            ca_file=ctx.config.ca_file,
        )
    try:
        return VaultKeyProvider(
            vault_url=str(ctx.config.vault_url or ""),
            vault_path=str(ctx.config.vault_path or ""),
            vault_token_env=ctx.config.vault_token_env,
            timeout_seconds=ctx.config.timeout_seconds,
            ca_file=ctx.config.ca_file,
            allow_insecure_tls=ctx.config.allow_insecure_tls,
        )
    except KeyProviderError as exc:
        raise CliUserError(
            message=f"Invalid key provider configuration: {exc}",
            code="config_invalid_key_provider",
            exit_code=2,
        ) from exc


def key_provider_metadata(ctx: CliContext, *, storage_dir: Path | None = None) -> dict[str, Any]:
    provider = build_key_provider(ctx, storage_dir=storage_dir)
    description = provider.describe()
    if isinstance(description, dict):
        return dict(description)
    return {"provider": ctx.config.key_provider}


def http_security_policy(ctx: CliContext) -> HttpSecurityPolicy:
    return HttpSecurityPolicy(
        allow_insecure_http=ctx.config.allow_insecure_http,
        allow_insecure_tls=ctx.config.allow_insecure_tls,
        ca_file=ctx.config.ca_file,
        mtls_enabled=ctx.config.mtls_enabled,
        cert_file=ctx.config.cert_file,
        key_file=ctx.config.key_file,
    )


def validation_http_security_policy(config: CliConfig) -> HttpSecurityPolicy:
    provider_backed_mtls = (
        config.key_provider == "vault"
        and config.mtls_enabled
        and not config.cert_file
        and not config.key_file
    )
    return HttpSecurityPolicy(
        allow_insecure_http=config.allow_insecure_http,
        allow_insecure_tls=config.allow_insecure_tls,
        ca_file=config.ca_file,
        mtls_enabled=False if provider_backed_mtls else config.mtls_enabled,
        cert_file=config.cert_file,
        key_file=config.key_file,
    )


def url_security_state(url: str | None) -> str:
    return security_state(url)


def http_security_profile(ctx: CliContext) -> str:
    return security_profile(http_security_policy(ctx))


def service_security_profile(service: dict[str, Any] | Any) -> str | None:
    if not isinstance(service, dict):
        return None
    http_hint = service.get("http")
    if isinstance(http_hint, dict):
        raw = http_hint.get("security_profile")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    relay_hint = service.get("relay")
    if isinstance(relay_hint, dict):
        raw = relay_hint.get("security_profile")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def runtime_status_path(storage_dir: Path, agent_id: str) -> Path:
    return storage_dir / "_runtime" / f"{sanitize_agent_id(agent_id)}.json"
