from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import ChessColor, PlayerRole, ReasoningEffort


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_role(value: str | None) -> PlayerRole:
    if value is None:
        return PlayerRole.INITIATOR
    normalized = value.strip().upper()
    return PlayerRole.__members__.get(normalized, PlayerRole.INITIATOR)


def _parse_color(value: str | None) -> ChessColor:
    if value is None:
        return ChessColor.WHITE
    normalized = value.strip().upper()
    return ChessColor.__members__.get(normalized, ChessColor.WHITE)


def _parse_effort(value: str | None) -> ReasoningEffort:
    try:
        return ReasoningEffort.from_value(value)
    except ValueError:
        return ReasoningEffort.MEDIUM


@dataclass(slots=True)
class AppConfig:
    server_port: int
    role: PlayerRole
    color: ChessColor
    local_agent_id: str
    remote_agent_id: str
    local_display_name: str
    remote_display_name: str
    public_base_url: str
    acp_message_path: str
    acp_storage_dir: str
    acp_discovery_scheme: str
    acp_relay_url: str | None
    acp_allow_insecure_http: bool
    acp_allow_insecure_tls: bool
    acp_ca_file: str | None
    acp_delivery_mode: str
    poll_interval_ms: int
    move_send_delay_ms: int
    match_timeout_seconds: int
    max_plies: int
    pgn_export_enabled: bool
    pgn_export_dir: str
    state_file: str
    reduced_motion: str
    reasoning_effort: ReasoningEffort
    openai_api_key: str | None
    openai_model: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        reduced_motion = (_env("CHESS_AGENT_UI_REDUCED_MOTION", "reduced") or "reduced").strip().lower()
        if reduced_motion not in {"off", "reduced", "system"}:
            reduced_motion = "reduced"

        delivery_mode = (_env("CHESS_AGENT_ACP_DELIVERY_MODE", "direct") or "direct").strip().lower()
        if delivery_mode not in {"auto", "direct", "relay", "amqp", "mqtt"}:
            delivery_mode = "direct"

        relay_url = _env("CHESS_AGENT_ACP_RELAY_URL")
        if relay_url is not None and not relay_url.strip():
            relay_url = None
        acp_ca_file = _env("CHESS_AGENT_ACP_CA_FILE")
        if acp_ca_file is not None and not acp_ca_file.strip():
            acp_ca_file = None

        return cls(
            server_port=_env_int("CHESS_AGENT_SERVER_PORT", 8088),
            role=_parse_role(_env("CHESS_AGENT_ROLE", "INITIATOR")),
            color=_parse_color(_env("CHESS_AGENT_COLOR", "WHITE")),
            local_agent_id=_env("CHESS_AGENT_LOCAL_AGENT_ID", "agent:player1@localhost:8088") or "agent:player1@localhost:8088",
            remote_agent_id=_env("CHESS_AGENT_REMOTE_AGENT_ID", "agent:player2@localhost:8089") or "agent:player2@localhost:8089",
            local_display_name=_env("CHESS_AGENT_LOCAL_DISPLAY_NAME", "Player 1 AI") or "Player 1 AI",
            remote_display_name=_env("CHESS_AGENT_REMOTE_DISPLAY_NAME", "Player 2 AI") or "Player 2 AI",
            public_base_url=_env("CHESS_AGENT_PUBLIC_BASE_URL", "http://localhost:8088") or "http://localhost:8088",
            acp_message_path=_env("CHESS_AGENT_ACP_MESSAGE_PATH", "/api/v1/acp/messages") or "/api/v1/acp/messages",
            acp_storage_dir=_env("CHESS_AGENT_ACP_STORAGE_DIR", "/var/lib/chess-agent/acp") or "/var/lib/chess-agent/acp",
            acp_discovery_scheme=_env("CHESS_AGENT_ACP_DISCOVERY_SCHEME", "http") or "http",
            acp_relay_url=relay_url,
            acp_allow_insecure_http=_env_bool("CHESS_AGENT_ACP_ALLOW_INSECURE_HTTP", False),
            acp_allow_insecure_tls=_env_bool("CHESS_AGENT_ACP_ALLOW_INSECURE_TLS", False),
            acp_ca_file=acp_ca_file.strip() if isinstance(acp_ca_file, str) else None,
            acp_delivery_mode=delivery_mode,
            poll_interval_ms=max(250, _env_int("CHESS_AGENT_POLL_INTERVAL_MS", 2000)),
            move_send_delay_ms=max(0, _env_int("CHESS_AGENT_MOVE_SEND_DELAY_MS", 2000)),
            match_timeout_seconds=max(30, _env_int("CHESS_AGENT_MATCH_TIMEOUT_SECONDS", 1800)),
            max_plies=max(10, _env_int("CHESS_AGENT_MAX_PLIES", 160)),
            pgn_export_enabled=_env_bool("CHESS_AGENT_PGN_EXPORT_ENABLED", True),
            pgn_export_dir=_env("CHESS_AGENT_PGN_EXPORT_DIR", "/var/lib/chess-agent/pgn") or "/var/lib/chess-agent/pgn",
            state_file=_env("CHESS_AGENT_STATE_FILE", "/var/lib/chess-agent/state/matches.json") or "/var/lib/chess-agent/state/matches.json",
            reduced_motion=reduced_motion,
            reasoning_effort=_parse_effort(_env("CHESS_AGENT_REASONING_EFFORT", "medium")),
            openai_api_key=_env("CHESS_AGENT_OPENAI_API_KEY"),
            openai_model=_env("CHESS_AGENT_OPENAI_MODEL", "o3-mini") or "o3-mini",
        )

    def resolve_acp_endpoint(self) -> str:
        base = self.public_base_url.strip()
        path = self.acp_message_path.strip()
        if base.endswith("/") and path.startswith("/"):
            return base[:-1] + path
        if not base.endswith("/") and not path.startswith("/"):
            return f"{base}/{path}"
        return base + path

    def ensure_paths(self) -> None:
        self.acp_storage_dir = str(
            self._mkdir_with_local_fallback(
                path=Path(self.acp_storage_dir),
                fallback=Path.cwd() / ".chess-agent" / "acp",
            ),
        )
        self.pgn_export_dir = str(
            self._mkdir_with_local_fallback(
                path=Path(self.pgn_export_dir),
                fallback=Path.cwd() / ".chess-agent" / "pgn",
            ),
        )
        self.state_file = str(
            self._mkdir_parent_with_local_fallback(
                file_path=Path(self.state_file),
                fallback=Path.cwd() / ".chess-agent" / "state" / "matches.json",
            ),
        )

    @staticmethod
    def _is_var_lib_chess_agent(path: Path) -> bool:
        return str(path).startswith("/var/lib/chess-agent")

    def _mkdir_with_local_fallback(self, *, path: Path, fallback: Path) -> Path:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except PermissionError:
            if not self._is_var_lib_chess_agent(path):
                raise
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def _mkdir_parent_with_local_fallback(self, *, file_path: Path, fallback: Path) -> Path:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            return file_path
        except PermissionError:
            if not self._is_var_lib_chess_agent(file_path.parent):
                raise
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback
