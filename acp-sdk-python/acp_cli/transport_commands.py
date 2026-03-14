from __future__ import annotations

import argparse
import socket
from typing import Any
from urllib.parse import urlparse

import requests

from acp.discovery import DiscoveryError
from acp.identity import read_identity

from .common import CliContext, CliUserError, build_discovery_client, identity_storage_dir


def register_transport_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="transport_command", required=True)

    list_cmd = subparsers.add_parser("list", help="List configured and supported transports")
    list_cmd.add_argument("--agent-id", required=True, help="ACP agent identifier")
    list_cmd.add_argument("--out-dir", help="Identity storage directory override")
    list_cmd.set_defaults(handler=handle_transport_list)

    probe_cmd = subparsers.add_parser("probe", help="Run lightweight transport probe checks")
    probe_cmd.add_argument("--agent-id", required=True, help="ACP agent identifier")
    probe_cmd.add_argument(
        "--transport",
        choices=["direct", "relay", "amqp", "mqtt", "http", "https"],
        help="Probe only one transport (default: probe all known transports)",
    )
    probe_cmd.add_argument("--out-dir", help="Identity storage directory override")
    probe_cmd.add_argument(
        "--relay-hint",
        action="append",
        default=None,
        help="Discovery relay hint override (repeatable)",
    )
    probe_cmd.add_argument(
        "--scheme",
        choices=["http", "https"],
        help="Discovery scheme override",
    )
    probe_cmd.set_defaults(handler=handle_transport_probe)


def handle_transport_list(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    identity_document, source = _resolve_identity_document(
        ctx,
        args.agent_id,
        out_dir=args.out_dir,
        relay_hints_override=None,
        scheme_override=None,
    )
    service = identity_document.get("service", {})
    capabilities = identity_document.get("capabilities", {})
    transports = capabilities.get("transports", [])
    return {
        "_human": [
            "Transport configuration",
            f"Agent ID: {args.agent_id}",
            f"Source: {source}",
            f"Supported transports: {', '.join(transports) or '-'}",
            f"Direct endpoint: {service.get('direct_endpoint')}",
            f"Relay hints: {', '.join(service.get('relay_hints', [])) or '-'}",
            f"AMQP configured: {'yes' if isinstance(service.get('amqp'), dict) else 'no'}",
            f"MQTT configured: {'yes' if isinstance(service.get('mqtt'), dict) else 'no'}",
        ],
        "ok": True,
        "agent_id": args.agent_id,
        "source": source,
        "supported_transports": transports,
        "service": {
            "direct_endpoint": service.get("direct_endpoint"),
            "relay_hints": service.get("relay_hints", []),
            "amqp": service.get("amqp"),
            "mqtt": service.get("mqtt"),
        },
        "supports": capabilities.get("supports", {}),
    }


def handle_transport_probe(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    identity_document, source = _resolve_identity_document(
        ctx,
        args.agent_id,
        out_dir=args.out_dir,
        relay_hints_override=args.relay_hint,
        scheme_override=args.scheme,
    )
    service = identity_document.get("service", {})
    capabilities = identity_document.get("capabilities", {})
    supported = [str(item) for item in capabilities.get("transports", [])]

    requested_transport = _normalize_transport(args.transport) if args.transport else None
    targets = [requested_transport] if requested_transport else ["direct", "relay", "amqp", "mqtt"]

    checks = [
        _probe_transport(
            transport=transport,
            service=service,
            timeout_seconds=ctx.config.timeout_seconds,
        )
        for transport in targets
    ]
    overall_ok = all(check["configured"] and (check.get("reachable") is not False) for check in checks)

    lines = [
        "Transport probe",
        f"Agent ID: {args.agent_id}",
        f"Source: {source}",
    ]
    for check in checks:
        lines.append(
            f"- {check['transport']}: configured={'yes' if check['configured'] else 'no'}"
            f", reachable={_render_reachable(check.get('reachable'))}, detail={check.get('detail') or '-'}",
        )

    return {
        "_human": lines,
        "_exit_code": 0 if overall_ok else 1,
        "ok": overall_ok,
        "agent_id": args.agent_id,
        "source": source,
        "supported_transports": supported,
        "checks": checks,
    }


def _resolve_identity_document(
    ctx: CliContext,
    agent_id: str,
    *,
    out_dir: str | None,
    relay_hints_override: list[str] | None,
    scheme_override: str | None,
) -> tuple[dict[str, Any], str]:
    storage_dir = identity_storage_dir(ctx, out_dir)
    bundle = read_identity(storage_dir, agent_id)
    if bundle is not None:
        _, identity_document = bundle
        return identity_document, "local"

    discovery = build_discovery_client(
        ctx,
        relay_hints_override=relay_hints_override,
        scheme_override=scheme_override,
    )
    try:
        identity_document = discovery.resolve(agent_id)
    except DiscoveryError as exc:
        raise CliUserError(
            message=f"Unable to resolve identity for transport operation: {exc}",
            code="transport_identity_not_found",
            details={"agent_id": agent_id},
            exit_code=2,
        ) from exc
    return identity_document, "discovery"


def _probe_transport(*, transport: str, service: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    if transport == "direct":
        endpoint = service.get("direct_endpoint")
        if not isinstance(endpoint, str) or not endpoint.strip():
            return {
                "transport": "direct",
                "configured": False,
                "reachable": None,
                "detail": "service.direct_endpoint is missing",
            }
        return {
            "transport": "direct",
            "configured": True,
            **_probe_http_endpoint(endpoint.strip(), timeout_seconds),
        }

    if transport == "relay":
        hints = service.get("relay_hints", [])
        relay_hints = [str(item) for item in hints if isinstance(item, str) and item.strip()]
        if not relay_hints:
            return {
                "transport": "relay",
                "configured": False,
                "reachable": None,
                "detail": "service.relay_hints is empty",
            }
        checks = [_probe_http_endpoint(f"{hint.rstrip('/')}/health", timeout_seconds) for hint in relay_hints]
        reachable = any(item["reachable"] for item in checks)
        return {
            "transport": "relay",
            "configured": True,
            "reachable": reachable,
            "detail": "at least one relay health check succeeded" if reachable else "relay health checks failed",
            "hints": relay_hints,
            "hint_checks": checks,
        }

    if transport == "amqp":
        amqp_service = service.get("amqp")
        broker = amqp_service.get("broker_url") if isinstance(amqp_service, dict) else None
        if not isinstance(broker, str) or not broker.strip():
            return {
                "transport": "amqp",
                "configured": False,
                "reachable": None,
                "detail": "service.amqp.broker_url is missing",
            }
        probe = _probe_tcp_endpoint(broker.strip(), timeout_seconds, default_port=5672)
        return {
            "transport": "amqp",
            "configured": True,
            **probe,
        }

    if transport == "mqtt":
        mqtt_service = service.get("mqtt")
        broker = mqtt_service.get("broker_url") if isinstance(mqtt_service, dict) else None
        topic = mqtt_service.get("topic") if isinstance(mqtt_service, dict) else None
        if not isinstance(broker, str) or not broker.strip():
            return {
                "transport": "mqtt",
                "configured": False,
                "reachable": None,
                "detail": "service.mqtt.broker_url is missing",
            }
        if not isinstance(topic, str) or not topic.strip():
            return {
                "transport": "mqtt",
                "configured": False,
                "reachable": None,
                "detail": "service.mqtt.topic is missing",
            }
        probe = _probe_tcp_endpoint(broker.strip(), timeout_seconds, default_port=1883)
        return {
            "transport": "mqtt",
            "configured": True,
            "topic": topic,
            **probe,
        }

    return {
        "transport": transport,
        "configured": False,
        "reachable": None,
        "detail": "Unsupported transport",
    }


def _probe_http_endpoint(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=timeout_seconds, allow_redirects=False)
        return {
            "reachable": True,
            "status_code": response.status_code,
            "detail": f"HTTP {response.status_code}",
            "target": url,
        }
    except requests.RequestException as exc:
        return {
            "reachable": False,
            "detail": str(exc),
            "target": url,
        }


def _probe_tcp_endpoint(url: str, timeout_seconds: int, *, default_port: int) -> dict[str, Any]:
    host, port = _parse_host_port(url, default_port=default_port)
    if host is None:
        return {
            "reachable": False,
            "detail": f"Unable to parse host/port from {url}",
            "target": url,
        }
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {
                "reachable": True,
                "detail": "TCP connect succeeded",
                "target": f"{host}:{port}",
            }
    except OSError as exc:
        return {
            "reachable": False,
            "detail": str(exc),
            "target": f"{host}:{port}",
        }


def _parse_host_port(url: str, *, default_port: int) -> tuple[str | None, int]:
    parsed = urlparse(url)
    if parsed.hostname:
        return parsed.hostname, parsed.port or default_port
    if "://" not in url:
        host, _, port_text = url.partition(":")
        if not host:
            return None, default_port
        if not port_text:
            return host, default_port
        try:
            return host, int(port_text)
        except Exception:
            return None, default_port
    return None, default_port


def _normalize_transport(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"http", "https"}:
        return "direct"
    if normalized in {"direct", "relay", "amqp", "mqtt"}:
        return normalized
    raise CliUserError(
        message=f"Unsupported transport: {value}",
        code="transport_invalid_args",
        exit_code=2,
    )


def _render_reachable(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"
