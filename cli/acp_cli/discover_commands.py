# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import argparse
from typing import Any

from acp.discovery import DiscoveryError

from .common import CliContext, CliUserError, build_discovery_client, url_security_state


def register_discover_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="discover_command", required=True)

    get_cmd = subparsers.add_parser("get", help="Resolve an ACP identity document via discovery")
    get_cmd.add_argument("--agent-id", required=True, help="Target ACP agent identifier")
    get_cmd.add_argument(
        "--relay-hint",
        action="append",
        default=None,
        help="Relay hint override for discovery requests (repeatable)",
    )
    get_cmd.add_argument(
        "--scheme",
        choices=["http", "https"],
        help="Discovery scheme override for .well-known lookups",
    )
    get_cmd.set_defaults(handler=handle_discover_get)

    list_cmd = subparsers.add_parser("list", help="List local discovery cache entries")
    list_cmd.set_defaults(handler=handle_discover_list)

    well_known_cmd = subparsers.add_parser(
        "well-known",
        help="Resolve ACP well-known metadata from a base URL",
    )
    well_known_cmd.add_argument(
        "base_url",
        help="Agent base URL (for example https://agent.example) or full /.well-known/acp URL",
    )
    well_known_cmd.add_argument(
        "--agent-id",
        help="Optional expected agent_id. Lookup fails if metadata does not match.",
    )
    well_known_cmd.set_defaults(handler=handle_discover_well_known)


def handle_discover_get(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    client = build_discovery_client(
        ctx,
        relay_hints_override=args.relay_hint,
        scheme_override=args.scheme,
    )
    try:
        identity_document = client.resolve(args.agent_id)
    except DiscoveryError as exc:
        raise CliUserError(
            message=f"Discovery failed for {args.agent_id}: {exc}",
            code="discovery_failed",
            details={
                "agent_id": args.agent_id,
                "scheme": args.scheme or ctx.config.discovery_scheme,
                "relay_hints": args.relay_hint or ctx.config.relay_hints,
            },
            exit_code=2,
        ) from exc

    summary = _identity_summary(identity_document)
    return {
        "_human": [
            "Discovery result",
            f"Agent ID: {summary['agent_id']}",
            f"Trust profile: {summary['trust_profile']}",
            f"Valid until: {summary['valid_until']}",
            f"Direct endpoint: {summary['service'].get('direct_endpoint')}",
            f"Direct endpoint security: {url_security_state(summary['service'].get('direct_endpoint'))}",
            f"Relay hints: {', '.join(summary['service'].get('relay_hints', [])) or '-'}",
            f"Transports: {', '.join(summary['transports']) or '-'}",
        ],
        "ok": True,
        "resolved": summary,
        "identity_document": identity_document,
    }


def handle_discover_list(_: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    client = build_discovery_client(ctx)
    entries: list[dict[str, Any]] = []
    for agent_id, cached in sorted(client.cache.items(), key=lambda item: item[0]):
        identity_document = cached.identity_document
        summary = _identity_summary(identity_document)
        summary["fetched_at"] = cached.fetched_at
        entries.append(summary)

    if entries:
        lines = ["Discovery cache"]
        for entry in entries:
            lines.append(
                f"- {entry['agent_id']} | fetched_at={entry.get('fetched_at')} | direct={entry['service'].get('direct_endpoint') or '-'}",
            )
    else:
        lines = ["Discovery cache is empty"]

    return {
        "_human": lines,
        "ok": True,
        "count": len(entries),
        "entries": entries,
        "cache_file": str(ctx.config.storage_dir / "discovery_cache.json"),
    }


def handle_discover_well_known(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    client = build_discovery_client(ctx)
    try:
        resolved = client.resolve_well_known(args.base_url, expected_agent_id=args.agent_id)
    except DiscoveryError as exc:
        raise CliUserError(
            message=f"Well-known discovery failed for {args.base_url}: {exc}",
            code="discover_well_known_failed",
            details={
                "base_url": args.base_url,
                "agent_id": args.agent_id,
            },
            exit_code=2,
        ) from exc
    identity_document = resolved["identity_document"]
    summary = _identity_summary(identity_document)
    well_known = resolved["well_known"]
    transport_names = sorted((well_known.get("transports") or {}).keys())
    return {
        "_human": [
            "Well-known discovery result",
            f"Well-known URL: {resolved['well_known_url']}",
            f"Agent ID: {well_known.get('agent_id')}",
            f"Identity document URL: {well_known.get('identity_document')}",
            f"Security profile: {well_known.get('security_profile') or '-'}",
            f"Transports: {', '.join(transport_names) or '-'}",
        ],
        "ok": True,
        "well_known_url": resolved["well_known_url"],
        "well_known": well_known,
        "resolved": summary,
        "identity_document": identity_document,
    }


def _identity_summary(identity_document: dict[str, Any]) -> dict[str, Any]:
    service = identity_document.get("service", {})
    capabilities = identity_document.get("capabilities", {})
    return {
        "agent_id": identity_document.get("agent_id"),
        "trust_profile": identity_document.get("trust_profile"),
        "created_at": identity_document.get("created_at"),
        "valid_until": identity_document.get("valid_until"),
        "service": {
            "direct_endpoint": service.get("direct_endpoint"),
            "relay_hints": service.get("relay_hints", []),
            "amqp": service.get("amqp"),
            "mqtt": service.get("mqtt"),
        },
        "security": {
            "direct_endpoint": url_security_state(service.get("direct_endpoint")),
            "relay_hints": [
                {"url": str(item), "state": url_security_state(str(item))}
                for item in service.get("relay_hints", [])
                if isinstance(item, str)
            ],
        },
        "transports": capabilities.get("transports", []),
        "message_classes": capabilities.get("message_classes", []),
    }
