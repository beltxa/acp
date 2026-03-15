from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from acp.http_security import HttpSecurityError, enforce_http_security

from .common import CliContext, http_security_policy, identity_storage_dir, url_security_state


def register_config_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="config_command", required=True)

    show_cmd = subparsers.add_parser("show", help="Show effective ACP CLI configuration")
    show_cmd.set_defaults(handler=handle_config_show)

    validate_cmd = subparsers.add_parser("validate", help="Validate endpoint/discovery transport security settings")
    validate_cmd.add_argument("--out-dir", help="Identity storage directory override")
    validate_cmd.set_defaults(handler=handle_config_validate)


def handle_config_show(_: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    config_dict = ctx.config.to_dict()
    return {
        "_human": [
            "CLI configuration",
            f"Config file: {ctx.config_path or '-'}",
            f"Storage dir: {ctx.config.storage_dir}",
            f"Discovery scheme: {ctx.config.discovery_scheme}",
            f"allow_insecure_http: {ctx.config.allow_insecure_http}",
            f"allow_insecure_tls: {ctx.config.allow_insecure_tls}",
            f"ca_file: {ctx.config.ca_file or '-'}",
        ],
        "ok": True,
        "config_file": str(ctx.config_path) if ctx.config_path else None,
        "config": config_dict,
    }


def handle_config_validate(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    if ctx.config.discovery_scheme.lower() == "http":
        _check_url(
            "http://discovery-scheme-placeholder.local",
            context="config.discovery_scheme=http",
            checks=checks,
            errors=errors,
            warnings=warnings,
            ctx=ctx,
            synthetic_target="discovery_scheme",
        )

    for relay_hint in ctx.config.relay_hints:
        _check_url(
            relay_hint,
            context="config.relay_hints",
            checks=checks,
            errors=errors,
            warnings=warnings,
            ctx=ctx,
        )
    for hint in ctx.config.enterprise_directory_hints:
        _check_url(
            hint,
            context="config.enterprise_directory_hints",
            checks=checks,
            errors=errors,
            warnings=warnings,
            ctx=ctx,
        )

    storage_dir = identity_storage_dir(ctx, args.out_dir)
    for identity_file in sorted(storage_dir.glob("*/identity_document.json")):
        try:
            identity_document = json.loads(identity_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{identity_file}: invalid JSON ({exc})")
            checks.append(
                {
                    "scope": "identity_document",
                    "target": str(identity_file),
                    "state": "invalid_json",
                    "ok": False,
                    "detail": str(exc),
                },
            )
            continue
        service = identity_document.get("service", {})
        direct_endpoint = service.get("direct_endpoint") if isinstance(service, dict) else None
        relay_hints = service.get("relay_hints", []) if isinstance(service, dict) else []
        if isinstance(direct_endpoint, str) and direct_endpoint.strip():
            _check_url(
                direct_endpoint.strip(),
                context=f"{identity_file}:service.direct_endpoint",
                checks=checks,
                errors=errors,
                warnings=warnings,
                ctx=ctx,
            )
        for relay_hint in relay_hints:
            if isinstance(relay_hint, str) and relay_hint.strip():
                _check_url(
                    relay_hint.strip(),
                    context=f"{identity_file}:service.relay_hints",
                    checks=checks,
                    errors=errors,
                    warnings=warnings,
                    ctx=ctx,
                )

    ok = not errors
    return {
        "_human": [
            "Config validation",
            f"Storage dir: {storage_dir}",
            f"Checks: {len(checks)}",
            f"Errors: {len(errors)}",
            f"Warnings: {len(warnings)}",
            *[f"Error: {item}" for item in errors[:10]],
            *[f"Warning: {item}" for item in warnings[:10]],
        ],
        "_exit_code": 0 if ok else 1,
        "ok": ok,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "storage_dir": str(storage_dir),
    }


def _check_url(
    url: str,
    *,
    context: str,
    checks: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
    ctx: CliContext,
    synthetic_target: str | None = None,
) -> None:
    try:
        warning_messages = enforce_http_security(url, policy=http_security_policy(ctx), context=context)
        check = {
            "scope": context,
            "target": synthetic_target or url,
            "state": url_security_state(url),
            "ok": True,
        }
        checks.append(check)
        warnings.extend(warning_messages)
    except HttpSecurityError as exc:
        check = {
            "scope": context,
            "target": synthetic_target or url,
            "state": url_security_state(url),
            "ok": False,
            "detail": str(exc),
        }
        checks.append(check)
        errors.append(str(exc))
