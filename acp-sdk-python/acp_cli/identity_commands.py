from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acp.capabilities import AgentCapabilities
from acp.http_security import HttpSecurityError, enforce_http_security
from acp.identity import (
    AgentIdentity,
    IdentityError,
    identity_path,
    read_identity,
    verify_identity_document,
    write_identity,
)

from .common import (
    CliContext,
    CliUserError,
    http_security_policy,
    http_security_profile,
    identity_storage_dir,
    key_provider_metadata,
    service_security_profile,
    url_security_state,
)


def register_identity_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="identity_command", required=True)

    create = subparsers.add_parser("create", help="Create a local ACP identity and identity document")
    create.add_argument("--agent-id", required=True, help="ACP agent identifier")
    create.add_argument("--out-dir", help="Identity storage directory override")
    create.add_argument(
        "--trust-profile",
        default="self_asserted",
        help="ACP trust profile",
    )
    create.add_argument("--direct-endpoint", help="Advertise direct endpoint in identity document")
    create.add_argument(
        "--relay-hint",
        action="append",
        default=None,
        help="Relay hint URL (repeatable)",
    )
    create.add_argument("--overwrite", action="store_true", help="Overwrite existing identity files")
    create.set_defaults(handler=handle_identity_create)

    show = subparsers.add_parser("show", help="Show local ACP identity metadata")
    show.add_argument("--agent-id", required=True, help="ACP agent identifier")
    show.add_argument("--out-dir", help="Identity storage directory override")
    show.set_defaults(handler=handle_identity_show)

    export = subparsers.add_parser("export", help="Export identity document to a file")
    export.add_argument("--agent-id", required=True, help="ACP agent identifier")
    export.add_argument("--out-dir", help="Identity storage directory override")
    export.add_argument("--out", required=True, help="Output file path")
    export.set_defaults(handler=handle_identity_export)

    verify = subparsers.add_parser("verify", help="Verify an identity document JSON file")
    verify.add_argument("--file", required=True, help="Path to identity document JSON")
    verify.set_defaults(handler=handle_identity_verify)


def handle_identity_create(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    storage_dir = identity_storage_dir(ctx, args.out_dir)
    agent_dir = identity_path(storage_dir, args.agent_id)

    existing = read_identity(storage_dir, args.agent_id)
    if existing is not None and not args.overwrite:
        raise CliUserError(
            message=f"Identity already exists for {args.agent_id}. Use --overwrite to replace it.",
            code="identity_exists",
            details={"agent_id": args.agent_id, "path": str(agent_dir)},
            exit_code=2,
        )

    if existing is not None and args.overwrite and agent_dir.exists():
        shutil.rmtree(agent_dir)

    try:
        identity = AgentIdentity.create(args.agent_id)
        capability_doc = AgentCapabilities(agent_id=args.agent_id).to_dict()
        relay_hints = args.relay_hint if args.relay_hint is not None else ctx.config.relay_hints
        warning_messages: list[str] = []
        if isinstance(args.direct_endpoint, str) and args.direct_endpoint.strip():
            warning_messages.extend(
                _validate_http_setting(
                    args.direct_endpoint.strip(),
                    ctx=ctx,
                    context="Identity direct endpoint",
                ),
            )
        for relay_hint in relay_hints:
            warning_messages.extend(
                _validate_http_setting(
                    str(relay_hint),
                    ctx=ctx,
                    context="Identity relay hint",
                ),
            )
        identity_document = identity.build_identity_document(
            direct_endpoint=args.direct_endpoint,
            relay_hints=relay_hints,
            http_security_profile="mtls" if ctx.config.mtls_enabled else None,
            relay_security_profile="mtls" if ctx.config.mtls_enabled else None,
            trust_profile=args.trust_profile,
            capabilities=capability_doc,
        )
    except IdentityError as exc:
        raise CliUserError(
            message=str(exc),
            code="identity_create_failed",
            details={"agent_id": args.agent_id},
            exit_code=2,
        ) from exc

    write_identity(storage_dir, identity, identity_document)
    provider_info = key_provider_metadata(ctx, storage_dir=storage_dir)
    return {
        "_human": [
            "Identity created",
            f"Agent ID: {args.agent_id}",
            f"Storage: {agent_dir}",
            f"Trust profile: {identity_document.get('trust_profile')}",
            f"Signing key ID: {identity.signing_kid}",
            f"Encryption key ID: {identity.encryption_kid}",
            f"Direct endpoint security: {url_security_state(args.direct_endpoint)}",
            f"HTTP security profile: {http_security_profile(ctx)}",
            f"Key provider: {provider_info.get('provider', ctx.config.key_provider)}",
            *[f"Warning: {message}" for message in warning_messages],
        ],
        "ok": True,
        "agent_id": args.agent_id,
        "storage_dir": str(storage_dir),
        "identity_path": str(agent_dir),
        "trust_profile": identity_document.get("trust_profile"),
        "signing_kid": identity.signing_kid,
        "encryption_kid": identity.encryption_kid,
        "public_keys": {
            "signing": identity.signing_public_key,
            "encryption": identity.encryption_public_key,
        },
        "service": identity_document.get("service", {}),
        "warnings": warning_messages,
        "security": {
            "direct_endpoint": url_security_state(args.direct_endpoint),
            "http_profile": http_security_profile(ctx),
            "relay_hints": [
                {"url": str(item), "state": url_security_state(str(item))}
                for item in relay_hints
                if isinstance(item, str)
            ],
        },
        "capabilities": {
            "transports": identity_document.get("capabilities", {}).get("transports", []),
            "message_classes": identity_document.get("capabilities", {}).get("message_classes", []),
        },
        "key_provider": provider_info,
        "created_at": identity_document.get("created_at"),
        "valid_until": identity_document.get("valid_until"),
    }


def handle_identity_show(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    storage_dir = identity_storage_dir(ctx, args.out_dir)
    bundle = read_identity(storage_dir, args.agent_id)
    if bundle is None:
        raise CliUserError(
            message=f"Identity not found for {args.agent_id}",
            code="identity_not_found",
            details={"agent_id": args.agent_id, "storage_dir": str(storage_dir)},
            exit_code=2,
        )

    identity, identity_document = bundle
    service = identity_document.get("service", {})
    provider_info = key_provider_metadata(ctx, storage_dir=storage_dir)
    public_keys = {
        "signing": identity_document.get("keys", {}).get("signing", {}),
        "encryption": identity_document.get("keys", {}).get("encryption", {}),
    }
    return {
        "_human": [
            "Identity summary",
            f"Agent ID: {identity_document.get('agent_id')}",
            f"Storage: {identity_path(storage_dir, args.agent_id)}",
            f"Trust profile: {identity_document.get('trust_profile')}",
            f"Valid until: {identity_document.get('valid_until')}",
            f"Direct endpoint: {service.get('direct_endpoint')}",
            f"Direct endpoint security: {url_security_state(service.get('direct_endpoint'))}",
            f"Relay hints: {', '.join(service.get('relay_hints', [])) or '-'}",
            f"HTTP security profile: {service_security_profile(service) or 'https'}",
            f"Key provider: {provider_info.get('provider', ctx.config.key_provider)}",
        ],
        "ok": True,
        "agent_id": identity_document.get("agent_id"),
        "storage_dir": str(storage_dir),
        "identity_path": str(identity_path(storage_dir, args.agent_id)),
        "trust_profile": identity_document.get("trust_profile"),
        "created_at": identity_document.get("created_at"),
        "valid_until": identity_document.get("valid_until"),
        "public_keys": public_keys,
        "service": service,
        "security": {
            "direct_endpoint": url_security_state(service.get("direct_endpoint")),
            "http_profile": service_security_profile(service),
            "relay_hints": [
                {"url": str(item), "state": url_security_state(str(item))}
                for item in service.get("relay_hints", [])
                if isinstance(item, str)
            ],
        },
        "capabilities": identity_document.get("capabilities", {}),
        "local_key_ids": {
            "signing_kid": identity.signing_kid,
            "encryption_kid": identity.encryption_kid,
        },
        "key_provider": provider_info,
    }


def handle_identity_export(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    storage_dir = identity_storage_dir(ctx, args.out_dir)
    bundle = read_identity(storage_dir, args.agent_id)
    if bundle is None:
        raise CliUserError(
            message=f"Identity not found for {args.agent_id}",
            code="identity_not_found",
            details={"agent_id": args.agent_id, "storage_dir": str(storage_dir)},
            exit_code=2,
        )
    _, identity_document = bundle

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(identity_document, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "_human": [
            "Identity document exported",
            f"Agent ID: {args.agent_id}",
            f"Output: {out_path}",
        ],
        "ok": True,
        "agent_id": args.agent_id,
        "output_file": str(out_path),
    }


def handle_identity_verify(args: argparse.Namespace, _: CliContext) -> dict[str, Any]:
    file_path = Path(args.file).expanduser()
    if not file_path.exists():
        raise CliUserError(
            message=f"Identity document file does not exist: {file_path}",
            code="identity_file_not_found",
            details={"file": str(file_path)},
            exit_code=2,
        )

    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CliUserError(
            message=f"Unable to parse identity document JSON: {exc}",
            code="identity_parse_failed",
            details={"file": str(file_path)},
            exit_code=2,
        ) from exc

    if not isinstance(raw, dict):
        raise CliUserError(
            message="Identity document must be a JSON object",
            code="identity_invalid_format",
            details={"file": str(file_path)},
            exit_code=2,
        )

    valid = verify_identity_document(raw)
    valid_until = raw.get("valid_until")
    is_expired = False
    if isinstance(valid_until, str):
        try:
            is_expired = datetime.fromisoformat(valid_until.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except Exception:
            is_expired = False

    return {
        "_human": [
            "Identity verification",
            f"File: {file_path}",
            f"Agent ID: {raw.get('agent_id')}",
            f"Valid: {'yes' if valid else 'no'}",
        ],
        "_exit_code": 0 if valid else 1,
        "ok": valid,
        "valid": valid,
        "file": str(file_path),
        "agent_id": raw.get("agent_id"),
        "trust_profile": raw.get("trust_profile"),
        "valid_until": valid_until,
        "expired": is_expired,
    }


def _validate_http_setting(
    url: str,
    *,
    ctx: CliContext,
    context: str,
) -> list[str]:
    try:
        return enforce_http_security(url, policy=http_security_policy(ctx), context=context)
    except HttpSecurityError as exc:
        raise CliUserError(
            message=str(exc),
            code="identity_insecure_http",
            exit_code=2,
        ) from exc
