from __future__ import annotations

import argparse
from typing import Any

from acp.relay_client import RelayClient
from acp.transport import TransportError

from .common import CliContext, CliUserError, build_http_transport, url_security_state


def register_relay_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="relay_command", required=True)

    status_cmd = subparsers.add_parser("status", help="Show relay runtime status")
    _add_relay_arg(status_cmd)
    status_cmd.set_defaults(handler=handle_relay_status)

    health_cmd = subparsers.add_parser("health", help="Check relay health")
    _add_relay_arg(health_cmd)
    health_cmd.set_defaults(handler=handle_relay_health)

    registry_cmd = subparsers.add_parser("registry", help="Inspect relay identity registry")
    registry_subparsers = registry_cmd.add_subparsers(dest="relay_registry_command", required=True)

    registry_list_cmd = registry_subparsers.add_parser("list", help="List relay registry entries")
    _add_relay_arg(registry_list_cmd)
    registry_list_cmd.add_argument("--limit", type=_positive_int, default=100, help="Maximum entries")
    registry_list_cmd.set_defaults(handler=handle_relay_registry_list)

    registry_show_cmd = registry_subparsers.add_parser("show", help="Show one relay registry entry")
    _add_relay_arg(registry_show_cmd)
    registry_show_cmd.add_argument("--agent-id", required=True, help="ACP agent identifier")
    registry_show_cmd.set_defaults(handler=handle_relay_registry_show)

    routes_cmd = subparsers.add_parser("routes", help="Inspect relay routing state")
    routes_subparsers = routes_cmd.add_subparsers(dest="relay_routes_command", required=True)

    routes_show_cmd = routes_subparsers.add_parser("show", help="Show relay route/pending-delivery state")
    _add_relay_arg(routes_show_cmd)
    routes_show_cmd.add_argument("--limit", type=_positive_int, default=100, help="Maximum pending routes")
    routes_show_cmd.set_defaults(handler=handle_relay_routes_show)

    ops_cmd = subparsers.add_parser("ops", help="Inspect relay operational metrics/failures")
    ops_subparsers = ops_cmd.add_subparsers(dest="relay_ops_command", required=True)

    ops_stats_cmd = ops_subparsers.add_parser("stats", help="Show relay operational statistics")
    _add_relay_arg(ops_stats_cmd)
    ops_stats_cmd.set_defaults(handler=handle_relay_ops_stats)

    ops_failures_cmd = ops_subparsers.add_parser("failures", help="Show recent relay delivery failures")
    _add_relay_arg(ops_failures_cmd)
    ops_failures_cmd.add_argument("--limit", type=_positive_int, default=100, help="Maximum failure rows")
    ops_failures_cmd.set_defaults(handler=handle_relay_ops_failures)


def handle_relay_status(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(client.status, code="relay_status_failed", relay=args.relay)
    store = payload.get("store", {}) if isinstance(payload.get("store"), dict) else {}
    routing = payload.get("routing", {}) if isinstance(payload.get("routing"), dict) else {}
    http_security = routing.get("http_security", {}) if isinstance(routing.get("http_security"), dict) else {}
    key_provider = (
        http_security.get("key_provider")
        if isinstance(http_security.get("key_provider"), dict)
        else {}
    )
    return {
        "_human": [
            "Relay status",
            f"Relay: {args.relay}",
            f"Relay security: {url_security_state(args.relay)}",
            f"Status: {payload.get('status', 'unknown')}",
            f"Version: {payload.get('relay_version')}",
            f"Registry entries: {payload.get('registry_count')}",
            f"Stored messages: {store.get('messages_total')}",
            f"Pending deliveries: {store.get('pending_deliveries_total')}",
            f"Store-and-forward: {'yes' if routing.get('store_and_forward') else 'no'}",
            f"allow_insecure_http: {http_security.get('allow_insecure_http')}",
            f"allow_insecure_tls: {http_security.get('allow_insecure_tls')}",
            f"mtls_enabled: {http_security.get('mtls_enabled')}",
            f"http_security_profile: {http_security.get('profile') or '-'}",
            f"key_provider: {key_provider.get('provider', '-')}",
            (
                f"vault_path: {key_provider.get('vault_path')}"
                if isinstance(key_provider.get("vault_path"), str)
                else "vault_path: -"
            ),
        ],
        "ok": payload.get("status") == "ok",
        "relay": args.relay,
        "security": {"relay": url_security_state(args.relay)},
        "status": payload,
    }


def handle_relay_health(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(client.health, code="relay_health_failed", relay=args.relay)
    status_value = payload.get("status")
    return {
        "_human": [
            "Relay health",
            f"Relay: {args.relay}",
            f"Relay security: {url_security_state(args.relay)}",
            f"Status: {status_value}",
        ],
        "ok": status_value == "ok",
        "relay": args.relay,
        "security": {"relay": url_security_state(args.relay)},
        "health": payload,
    }


def handle_relay_registry_list(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(
        lambda: client.registry_list(limit=args.limit),
        code="relay_registry_list_failed",
        relay=args.relay,
    )
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    return {
        "_human": [
            "Relay registry entries",
            f"Relay: {args.relay}",
            f"Count: {payload.get('count', len(items))}",
            f"Returned: {len(items)}",
        ],
        "ok": True,
        "relay": args.relay,
        "count": payload.get("count", len(items)),
        "items": items,
    }


def handle_relay_registry_show(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(
        lambda: client.registry_show(args.agent_id),
        code="relay_registry_show_failed",
        relay=args.relay,
        extra={"agent_id": args.agent_id},
    )
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    return {
        "_human": [
            "Relay registry entry",
            f"Relay: {args.relay}",
            f"Agent ID: {summary.get('agent_id') or args.agent_id}",
            f"Trust profile: {summary.get('trust_profile')}",
            f"Valid until: {summary.get('valid_until')}",
        ],
        "ok": True,
        "relay": args.relay,
        "agent_id": args.agent_id,
        "entry": payload,
    }


def handle_relay_routes_show(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(
        lambda: client.routes_show(limit=args.limit),
        code="relay_routes_show_failed",
        relay=args.relay,
    )
    pending = payload.get("pending", []) if isinstance(payload.get("pending"), list) else []
    return {
        "_human": [
            "Relay routing",
            f"Relay: {args.relay}",
            f"Pending deliveries: {payload.get('pending_count', len(pending))}",
            f"Returned pending entries: {len(pending)}",
        ],
        "ok": True,
        "relay": args.relay,
        "routes": payload,
    }


def handle_relay_ops_stats(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(client.ops_stats, code="relay_ops_stats_failed", relay=args.relay)
    store = payload.get("store", {}) if isinstance(payload.get("store"), dict) else {}
    return {
        "_human": [
            "Relay ops stats",
            f"Relay: {args.relay}",
            f"Messages total: {store.get('messages_total')}",
            f"Outcomes total: {store.get('outcomes_total')}",
            f"Failure outcomes: {store.get('failure_outcomes_total')}",
            f"Pending retries: {store.get('pending_retries_total')}",
        ],
        "ok": payload.get("status") == "ok",
        "relay": args.relay,
        "stats": payload,
    }


def handle_relay_ops_failures(args: argparse.Namespace, _ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(_ctx))
    payload = _safe_call(
        lambda: client.ops_failures(limit=args.limit),
        code="relay_ops_failures_failed",
        relay=args.relay,
    )
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    return {
        "_human": [
            "Relay ops failures",
            f"Relay: {args.relay}",
            f"Failures: {payload.get('count', len(items))}",
            f"Returned rows: {len(items)}",
        ],
        "ok": True,
        "relay": args.relay,
        "count": payload.get("count", len(items)),
        "items": items,
    }


def _add_relay_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--relay", required=True, help="Relay base URL")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _safe_call(
    fn: Any,
    *,
    code: str,
    relay: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        result = fn()
    except TransportError as exc:
        details = {"relay": relay}
        if extra:
            details.update(extra)
        raise CliUserError(
            message=f"Relay request failed: {exc}",
            code=code,
            details=details,
            exit_code=2,
        ) from exc
    if not isinstance(result, dict):
        details = {"relay": relay}
        if extra:
            details.update(extra)
        raise CliUserError(
            message="Relay response must be a JSON object",
            code=code,
            details=details,
            exit_code=2,
        )
    return result
