from __future__ import annotations

import argparse
import importlib.metadata
from typing import Any, Sequence

from .agent_commands import register_agent_commands
from .common import CliContext, CliUserError, load_cli_config
from .config_commands import register_config_commands
from .discover_commands import register_discover_commands
from .identity_commands import register_identity_commands
from .message_commands import register_message_commands
from .output import emit_error, emit_result
from .relay_commands import register_relay_commands
from .register_commands import register_register_commands
from .transport_commands import register_transport_commands


def build_parser() -> argparse.ArgumentParser:
    version_text = _resolve_cli_version()
    parser = argparse.ArgumentParser(
        prog="acp",
        description=(
            "ACP CLI v1 (Phase 4): identity, discovery, registration, messaging, "
            "agent runtime, transport operations, and relay inspection"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"acp {version_text}",
        help="Show ACP CLI version and exit",
    )
    parser.add_argument("--config", help="Path to ACP CLI config JSON file")
    parser.add_argument("--storage-dir", help="Override local ACP storage directory")
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow http:// endpoints for local/dev/demo workflows",
    )
    parser.add_argument(
        "--allow-insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for https:// endpoints",
    )
    parser.add_argument(
        "--mtls-enabled",
        action="store_true",
        help="Enable optional HTTP mTLS profile (requires --cert-file and --key-file)",
    )
    parser.add_argument("--ca-file", help="Custom CA bundle path for HTTPS verification")
    parser.add_argument("--cert-file", help="Client/server certificate path for mTLS profile")
    parser.add_argument("--key-file", help="Client/server private key path for mTLS profile")
    parser.add_argument(
        "--key-provider",
        choices=["local", "vault"],
        help="Key provider backend for identity/TLS material",
    )
    parser.add_argument("--vault-url", help="Vault base URL when --key-provider=vault")
    parser.add_argument("--vault-path", help="Vault secret path prefix when --key-provider=vault")
    parser.add_argument(
        "--vault-token-env",
        help="Environment variable name that contains the Vault token",
    )
    parser.add_argument("--json", action="store_true", help="Emit command output as JSON")

    domains = parser.add_subparsers(dest="domain", required=True)

    identity = domains.add_parser("identity", help="Identity operations")
    register_identity_commands(identity)

    discover = domains.add_parser("discover", help="Discovery operations")
    register_discover_commands(discover)

    register = domains.add_parser("register", help="Registration operations")
    register_register_commands(register)

    message = domains.add_parser("message", help="Messaging operations")
    register_message_commands(message)

    agent = domains.add_parser("agent", help="Agent runtime operations")
    register_agent_commands(agent)

    transport = domains.add_parser("transport", help="Transport operations")
    register_transport_commands(transport)

    relay = domains.add_parser("relay", help="Relay inspection operations")
    register_relay_commands(relay)

    config = domains.add_parser("config", help="CLI/runtime configuration operations")
    register_config_commands(config)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        config, config_path = load_cli_config(
            args.config,
            args.storage_dir,
            allow_insecure_http_override=True if args.allow_insecure_http else None,
            allow_insecure_tls_override=True if args.allow_insecure_tls else None,
            mtls_enabled_override=True if args.mtls_enabled else None,
            ca_file_override=args.ca_file,
            cert_file_override=args.cert_file,
            key_file_override=args.key_file,
            key_provider_override=args.key_provider,
            vault_url_override=args.vault_url,
            vault_path_override=args.vault_path,
            vault_token_env_override=args.vault_token_env,
        )
        ctx = CliContext(config=config, json_output=bool(args.json), config_path=config_path)

        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 2

        result = handler(args, ctx)
        if not isinstance(result, dict):
            raise RuntimeError("command handler must return a dict result")
        emit_result(result, json_output=ctx.json_output)
        return int(result.get("_exit_code", 0))
    except CliUserError as exc:
        emit_error(exc, json_output=bool(getattr(args, "json", False)))
        return int(exc.exit_code)
    except Exception as exc:  # noqa: BLE001
        emit_error(exc, json_output=bool(getattr(args, "json", False)))
        return 1


def run() -> None:
    raise SystemExit(main())


def _resolve_cli_version() -> str:
    for distribution_name in ("acp-sdk", "acp-sdk-python"):
        try:
            return importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "dev"


if __name__ == "__main__":
    run()
