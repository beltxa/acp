from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import os
from typing import Any

from acp.discovery import DiscoveryClient
from acp.identity import sanitize_agent_id


DEFAULT_CONFIG_PATH = Path.home() / ".acp" / "config.json"


@dataclass
class CliConfig:
    storage_dir: Path = Path(".acp-data")
    discovery_scheme: str = "https"
    relay_hints: list[str] = field(default_factory=list)
    enterprise_directory_hints: list[str] = field(default_factory=list)
    timeout_seconds: int = 5

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
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "storage_dir": str(self.storage_dir),
            "discovery_scheme": self.discovery_scheme,
            "relay_hints": self.relay_hints,
            "enterprise_directory_hints": self.enterprise_directory_hints,
            "timeout_seconds": self.timeout_seconds,
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


def load_cli_config(config_path_arg: str | None, storage_dir_override: str | None) -> tuple[CliConfig, Path | None]:
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
    config.storage_dir.mkdir(parents=True, exist_ok=True)
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
    )


def runtime_status_path(storage_dir: Path, agent_id: str) -> Path:
    return storage_dir / "_runtime" / f"{sanitize_agent_id(agent_id)}.json"
