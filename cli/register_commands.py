from __future__ import annotations

import argparse
from typing import Any

from acp.amqp_transport import DEFAULT_AMQP_EXCHANGE, build_amqp_service_hint
from acp.http_security import HttpSecurityError, HttpSecurityPolicy, enforce_http_security
from acp.identity import read_identity, verify_identity_document, write_identity
from acp.mqtt_transport import DEFAULT_MQTT_QOS, build_mqtt_service_hint
from acp.relay_client import RelayClient
from acp.transport import TransportError

from .common import (
    CliContext,
    CliUserError,
    build_http_transport,
    http_security_policy,
    http_security_profile,
    identity_storage_dir,
    service_security_profile,
    url_security_state,
)


def register_register_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="register_command", required=True)

    put_cmd = subparsers.add_parser("put", help="Publish local identity registration to relay")
    _add_register_common_args(put_cmd)
    put_cmd.set_defaults(handler=handle_register_put)

    update_cmd = subparsers.add_parser("update", help="Update relay registration for an existing local identity")
    _add_register_common_args(update_cmd)
    update_cmd.set_defaults(handler=handle_register_update)

    show_cmd = subparsers.add_parser("show", help="Show relay registration state for an agent")
    show_cmd.add_argument("--agent-id", required=True, help="ACP agent identifier")
    show_cmd.add_argument("--relay", required=True, help="Relay base URL")
    show_cmd.set_defaults(handler=handle_register_show)


def handle_register_put(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    return _register_publish(args, ctx, mode="put")


def handle_register_update(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    return _register_publish(args, ctx, mode="update")


def handle_register_show(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(args.relay, transport=build_http_transport(ctx))
    try:
        identity_document = client.discover_identity(args.agent_id)
    except TransportError as exc:
        raise CliUserError(
            message=f"Unable to fetch registration from relay {args.relay}: {exc}",
            code="register_show_failed",
            details={"agent_id": args.agent_id, "relay": args.relay},
            exit_code=2,
        ) from exc

    service = identity_document.get("service", {})
    direct_endpoint = service.get("direct_endpoint")
    relay_hints = service.get("relay_hints", [])
    return {
        "_human": [
            "Relay registration",
            f"Agent ID: {identity_document.get('agent_id')}",
            f"Relay: {args.relay}",
            f"Direct endpoint: {direct_endpoint}",
            f"Direct endpoint security: {url_security_state(direct_endpoint if isinstance(direct_endpoint, str) else None)}",
            f"Relay security: {url_security_state(args.relay)}",
            f"Relay hints: {', '.join(relay_hints) or '-'}",
            f"HTTP security profile: {service_security_profile(service) or 'https'}",
            f"AMQP: {'configured' if isinstance(service.get('amqp'), dict) else 'not configured'}",
            f"MQTT: {'configured' if isinstance(service.get('mqtt'), dict) else 'not configured'}",
        ],
        "ok": True,
        "agent_id": identity_document.get("agent_id"),
        "relay": args.relay,
        "identity_document": identity_document,
        "service": {
            "direct_endpoint": service.get("direct_endpoint"),
            "relay_hints": service.get("relay_hints", []),
            "amqp": service.get("amqp"),
            "mqtt": service.get("mqtt"),
        },
        "security": {
            "relay": url_security_state(args.relay),
            "direct_endpoint": url_security_state(direct_endpoint if isinstance(direct_endpoint, str) else None),
            "relay_hints": [
                {"url": str(item), "state": url_security_state(str(item))}
                for item in relay_hints
                if isinstance(item, str)
            ],
            "http_profile": (
                service.get("http", {}).get("security_profile")
                if isinstance(service.get("http"), dict)
                else None
            ),
            "relay_profile": (
                service.get("relay", {}).get("security_profile")
                if isinstance(service.get("relay"), dict)
                else None
            ),
        },
    }


def _register_publish(args: argparse.Namespace, ctx: CliContext, *, mode: str) -> dict[str, Any]:
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
    updated_service, warning_messages = _apply_overrides(
        agent_id=args.agent_id,
        service=identity_document.get("service", {}),
        endpoint=args.endpoint,
        relay=args.relay,
        transport=args.transport,
        broker=args.broker,
        topic=args.topic,
        exchange=args.exchange,
        qos=args.qos,
        policy=http_security_policy(ctx),
    )
    updated_document = identity.build_identity_document(
        direct_endpoint=updated_service.get("direct_endpoint"),
        relay_hints=[str(item) for item in updated_service.get("relay_hints", [])],
        http_security_profile="mtls" if ctx.config.mtls_enabled else None,
        relay_security_profile="mtls" if ctx.config.mtls_enabled else None,
        amqp_service=updated_service.get("amqp") if isinstance(updated_service.get("amqp"), dict) else None,
        mqtt_service=updated_service.get("mqtt") if isinstance(updated_service.get("mqtt"), dict) else None,
        trust_profile=str(identity_document.get("trust_profile", "self_asserted")),
        capabilities=identity_document.get("capabilities", {}),
    )

    if not verify_identity_document(updated_document):
        raise CliUserError(
            message="Updated identity document failed verification",
            code="identity_invalid",
            details={"agent_id": args.agent_id},
            exit_code=2,
        )

    # Persist local identity document update before publishing to keep local/remote aligned.
    write_identity(storage_dir, identity, updated_document)

    client = RelayClient(args.relay, transport=build_http_transport(ctx))
    try:
        relay_response = client.register_identity_document(updated_document)
    except TransportError as exc:
        raise CliUserError(
            message=f"Relay registration failed: {exc}",
            code="register_publish_failed",
            details={"agent_id": args.agent_id, "relay": args.relay},
            exit_code=2,
        ) from exc

    service = updated_document.get("service", {})
    direct_endpoint = service.get("direct_endpoint")
    relay_hints = service.get("relay_hints", [])
    return {
        "_human": [
            "Relay registration published",
            f"Mode: {mode}",
            f"Agent ID: {args.agent_id}",
            f"Relay: {args.relay}",
            f"Direct endpoint: {direct_endpoint}",
            f"Direct endpoint security: {url_security_state(direct_endpoint if isinstance(direct_endpoint, str) else None)}",
            f"Relay security: {url_security_state(args.relay)}",
            f"Relay hints: {', '.join(relay_hints) or '-'}",
            f"HTTP security profile: {http_security_profile(ctx)}",
            *[f"Warning: {message}" for message in warning_messages],
        ],
        "ok": True,
        "mode": mode,
        "agent_id": args.agent_id,
        "relay": args.relay,
        "relay_response": relay_response,
        "service": service,
        "warnings": warning_messages,
        "security": {
            "relay": url_security_state(args.relay),
            "direct_endpoint": url_security_state(direct_endpoint if isinstance(direct_endpoint, str) else None),
            "relay_hints": [
                {"url": str(item), "state": url_security_state(str(item))}
                for item in relay_hints
                if isinstance(item, str)
            ],
            "http_profile": (
                service.get("http", {}).get("security_profile")
                if isinstance(service.get("http"), dict)
                else None
            ),
            "relay_profile": (
                service.get("relay", {}).get("security_profile")
                if isinstance(service.get("relay"), dict)
                else None
            ),
        },
    }


def _apply_overrides(
    *,
    agent_id: str,
    service: dict[str, Any] | Any,
    endpoint: str | None,
    relay: str,
    transport: str | None,
    broker: str | None,
    topic: str | None,
    exchange: str | None,
    qos: int | None,
    policy: HttpSecurityPolicy,
) -> tuple[dict[str, Any], list[str]]:
    service = dict(service if isinstance(service, dict) else {})
    warning_messages: list[str] = []

    warning_messages.extend(
        _validate_http_setting(relay, policy=policy, context="Registration relay URL"),
    )
    relay_hints = [str(item) for item in service.get("relay_hints", []) if str(item).strip()]
    if relay not in relay_hints:
        relay_hints.append(relay)
    service["relay_hints"] = relay_hints

    if endpoint is not None and endpoint.strip():
        normalized_endpoint = endpoint.strip()
        warning_messages.extend(
            _validate_http_setting(
                normalized_endpoint,
                policy=policy,
                context="Registration direct endpoint",
            ),
        )
        service["direct_endpoint"] = normalized_endpoint

    effective_transport = _resolve_transport(
        transport=transport,
        broker=broker,
        topic=topic,
        exchange=exchange,
        qos=qos,
    )
    if effective_transport == "amqp":
        broker_url = (
            broker
            or _service_value(service.get("amqp"), "broker_url")
        )
        if not broker_url:
            raise CliUserError(
                message="AMQP registration requires --broker (or existing service.amqp.broker_url)",
                code="register_invalid_args",
                exit_code=2,
            )
        exchange_name = exchange or _service_value(service.get("amqp"), "exchange") or DEFAULT_AMQP_EXCHANGE
        service["amqp"] = build_amqp_service_hint(
            agent_id=agent_id,
            broker_url=broker_url,
            exchange=exchange_name,
        )
    elif exchange is not None:
        raise CliUserError(
            message="--exchange may only be used with --transport amqp",
            code="register_invalid_args",
            exit_code=2,
        )

    if effective_transport == "mqtt":
        broker_url = (
            broker
            or _service_value(service.get("mqtt"), "broker_url")
        )
        if not broker_url:
            raise CliUserError(
                message="MQTT registration requires --broker (or existing service.mqtt.broker_url)",
                code="register_invalid_args",
                exit_code=2,
            )
        topic_value = topic or _service_value(service.get("mqtt"), "topic")
        qos_value = qos if qos is not None else _service_int(service.get("mqtt"), "qos")
        service["mqtt"] = build_mqtt_service_hint(
            agent_id=agent_id,
            broker_url=broker_url,
            topic=topic_value,
            qos=qos_value if qos_value is not None else DEFAULT_MQTT_QOS,
        )
    elif topic is not None or qos is not None:
        raise CliUserError(
            message="--topic/--qos may only be used with --transport mqtt",
            code="register_invalid_args",
            exit_code=2,
        )

    direct_endpoint = service.get("direct_endpoint")
    if isinstance(direct_endpoint, str) and direct_endpoint.strip():
        warning_messages.extend(
            _validate_http_setting(
                direct_endpoint.strip(),
                policy=policy,
                context="Registration direct endpoint",
            ),
        )
    for relay_hint in relay_hints:
        warning_messages.extend(
            _validate_http_setting(
                relay_hint,
                policy=policy,
                context="Registration relay hint",
            ),
        )

    deduped_warnings: list[str] = []
    for message in warning_messages:
        if message not in deduped_warnings:
            deduped_warnings.append(message)
    return service, deduped_warnings


def _validate_http_setting(
    url: str,
    *,
    policy: HttpSecurityPolicy,
    context: str,
) -> list[str]:
    try:
        return enforce_http_security(url, policy=policy, context=context)
    except HttpSecurityError as exc:
        raise CliUserError(
            message=str(exc),
            code="register_insecure_http",
            exit_code=2,
        ) from exc


def _resolve_transport(
    *,
    transport: str | None,
    broker: str | None,
    topic: str | None,
    exchange: str | None,
    qos: int | None,
) -> str | None:
    if transport:
        normalized = transport.strip().lower()
        if normalized in {"http", "https"}:
            return "direct"
        if normalized in {"direct", "relay", "amqp", "mqtt"}:
            return normalized
        raise CliUserError(
            message=f"Unsupported transport: {transport}",
            code="register_invalid_args",
            exit_code=2,
        )

    inferred = set()
    if exchange is not None:
        inferred.add("amqp")
    if topic is not None or qos is not None:
        inferred.add("mqtt")
    if broker is not None:
        inferred.update({"amqp", "mqtt"})

    if len(inferred) > 1:
        raise CliUserError(
            message="Unable to infer transport from options. Specify --transport amqp|mqtt.",
            code="register_invalid_args",
            exit_code=2,
        )
    if len(inferred) == 1:
        return next(iter(inferred))
    return None


def _service_value(service_value: Any, key: str) -> str | None:
    if isinstance(service_value, dict) and isinstance(service_value.get(key), str):
        value = str(service_value.get(key)).strip()
        return value or None
    return None


def _service_int(service_value: Any, key: str) -> int | None:
    if not isinstance(service_value, dict):
        return None
    raw = service_value.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _add_register_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent-id", required=True, help="ACP agent identifier")
    parser.add_argument("--relay", required=True, help="Relay base URL")
    parser.add_argument("--out-dir", help="Identity storage directory override")
    parser.add_argument("--endpoint", help="Direct endpoint to advertise")
    parser.add_argument(
        "--transport",
        choices=["direct", "relay", "amqp", "mqtt", "http", "https"],
        help="Primary transport hint to update",
    )
    parser.add_argument("--broker", help="Broker URL for transport hint updates")
    parser.add_argument("--topic", help="MQTT topic hint")
    parser.add_argument("--exchange", help="AMQP exchange hint")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], help="MQTT QoS hint")
