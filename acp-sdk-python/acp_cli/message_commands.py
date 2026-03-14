from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp.agent import Agent
from acp.messages import MessageClass

from .common import CliContext, CliUserError


def register_message_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="message_command", required=True)

    send_cmd = subparsers.add_parser("send", help="Send ACP message payload to one or more recipients")
    send_cmd.add_argument("--from", dest="from_agent", required=True, help="Sender ACP agent identifier")
    send_cmd.add_argument("--to", action="append", required=True, help="Recipient ACP agent identifier (repeatable)")
    payload_group = send_cmd.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--payload-file", help="Path to JSON payload file")
    payload_group.add_argument("--payload-json", help="Inline JSON payload")
    send_cmd.add_argument("--context", help="ACP context id")
    send_cmd.add_argument(
        "--transport",
        choices=["auto", "direct", "relay", "amqp", "mqtt", "http", "https"],
        help="Transport override (mapped to delivery mode)",
    )
    send_cmd.add_argument(
        "--delivery-mode",
        choices=["auto", "direct", "relay", "amqp", "mqtt"],
        help="Delivery mode override",
    )
    send_cmd.add_argument("--expires-in", type=int, default=300, help="Message expiry in seconds")
    send_cmd.add_argument("--relay", help="Relay URL override for sender runtime")
    send_cmd.set_defaults(handler=handle_message_send)

    capabilities_cmd = subparsers.add_parser("capabilities", help="Request recipient ACP capabilities")
    capabilities_cmd.add_argument("--from", dest="from_agent", required=True, help="Sender ACP agent identifier")
    capabilities_cmd.add_argument("--to", required=True, help="Recipient ACP agent identifier")
    capabilities_cmd.add_argument(
        "--transport",
        choices=["auto", "direct", "relay", "amqp", "mqtt", "http", "https"],
        help="Transport override (mapped to delivery mode)",
    )
    capabilities_cmd.add_argument(
        "--delivery-mode",
        choices=["auto", "direct", "relay", "amqp", "mqtt"],
        help="Delivery mode override",
    )
    capabilities_cmd.add_argument("--relay", help="Relay URL override for sender runtime")
    capabilities_cmd.set_defaults(handler=handle_message_capabilities)


def handle_message_send(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    payload = _load_payload(args.payload_file, args.payload_json)
    if args.expires_in <= 0:
        raise CliUserError(
            message="--expires-in must be > 0",
            code="message_invalid_args",
            exit_code=2,
        )

    mode = _resolve_delivery_mode(args.transport, args.delivery_mode)
    agent = _load_agent(ctx, args.from_agent, args.relay)

    result = agent.send(
        recipients=args.to,
        payload=payload,
        context=args.context,
        expires_in_seconds=args.expires_in,
        delivery_mode=mode,
    )

    outcome_summary = [_outcome_to_dict(outcome) for outcome in result.outcomes]
    success_count = sum(1 for item in outcome_summary if item["state"] in {"DELIVERED", "ACKNOWLEDGED"})
    return {
        "_human": [
            "Message send result",
            f"Sender: {args.from_agent}",
            f"Recipients: {', '.join(args.to)}",
            f"Delivery mode: {mode}",
            f"Operation ID: {result.operation_id}",
            f"Message ID: {result.message_id}",
            f"Success outcomes: {success_count}/{len(outcome_summary)}",
        ],
        "ok": True,
        "sender": args.from_agent,
        "recipients": args.to,
        "delivery_mode": mode,
        "context": args.context,
        "expires_in": args.expires_in,
        "result": result.to_dict(),
        "outcomes": outcome_summary,
    }


def handle_message_capabilities(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    mode = _resolve_delivery_mode(args.transport, args.delivery_mode)
    agent = _load_agent(ctx, args.from_agent, args.relay)

    response_payload: dict[str, Any] | None
    if mode == "auto":
        send_result, response_payload = agent.request_capabilities(args.to)
    else:
        send_result = agent.send(
            recipients=[args.to],
            payload={"request": "capabilities"},
            message_class=MessageClass.CAPABILITIES,
            context=f"capabilities:{uuid4()}",
            delivery_mode=mode,
        )
        response_payload = _extract_capabilities_response(agent, send_result.to_dict())

    response_status = "response_received" if response_payload is not None else "request_sent_no_response"
    return {
        "_human": [
            "Capabilities request result",
            f"Sender: {args.from_agent}",
            f"Recipient: {args.to}",
            f"Delivery mode: {mode}",
            f"Operation ID: {send_result.operation_id}",
            f"Capabilities received: {'yes' if response_payload is not None else 'no'}",
            (
                "Result: request sent, no response received"
                if response_payload is None
                else "Result: capabilities response received"
            ),
        ],
        "ok": True,
        "sender": args.from_agent,
        "recipient": args.to,
        "delivery_mode": mode,
        "response_status": response_status,
        "result": send_result.to_dict(),
        "capabilities": response_payload,
    }


def _extract_capabilities_response(agent: Agent, send_result: dict[str, Any]) -> dict[str, Any] | None:
    outcomes = send_result.get("outcomes")
    if not isinstance(outcomes, list):
        return None
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        response_message = outcome.get("response_message")
        if not isinstance(response_message, dict):
            continue
        try:
            response, payload = agent.decrypt_message_for_self(response_message)
        except Exception:
            continue
        if response.envelope.message_class is MessageClass.CAPABILITIES:
            return payload
    return None


def _load_agent(ctx: CliContext, agent_id: str, relay: str | None) -> Agent:
    kwargs: dict[str, Any] = {
        "storage_dir": ctx.config.storage_dir,
        "discovery_scheme": ctx.config.discovery_scheme,
        "relay_hints": ctx.config.relay_hints,
        "enterprise_directory_hints": ctx.config.enterprise_directory_hints,
    }
    if relay is not None and relay.strip():
        kwargs["relay_url"] = relay.strip()
        kwargs["relay_hints"] = [relay.strip(), *ctx.config.relay_hints]
    return Agent.load_or_create(agent_id, **kwargs)


def _load_payload(payload_file: str | None, payload_json: str | None) -> dict[str, Any]:
    if payload_file is not None:
        file_path = Path(payload_file).expanduser()
        if not file_path.exists():
            raise CliUserError(
                message=f"Payload file not found: {file_path}",
                code="payload_file_not_found",
                details={"file": str(file_path)},
                exit_code=2,
            )
        raw_text = file_path.read_text(encoding="utf-8")
        source = str(file_path)
    else:
        raw_text = payload_json or ""
        source = "inline JSON"

    try:
        parsed = json.loads(raw_text)
    except Exception as exc:
        raise CliUserError(
            message=f"Invalid JSON payload from {source}: {exc}",
            code="payload_parse_failed",
            exit_code=2,
        ) from exc

    if not isinstance(parsed, dict):
        raise CliUserError(
            message="Payload must be a JSON object",
            code="payload_invalid_format",
            details={"source": source},
            exit_code=2,
        )
    return parsed


def _resolve_delivery_mode(transport: str | None, delivery_mode: str | None) -> str:
    mode_from_transport = _normalize_mode(transport)
    mode_from_delivery = _normalize_mode(delivery_mode)

    if mode_from_transport and mode_from_delivery and mode_from_transport != mode_from_delivery:
        raise CliUserError(
            message=(
                f"Conflicting mode options: --transport={transport} and --delivery-mode={delivery_mode}"
            ),
            code="message_invalid_args",
            exit_code=2,
        )
    return mode_from_delivery or mode_from_transport or "auto"


def _normalize_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"http", "https"}:
        return "direct"
    if normalized in {"auto", "direct", "relay", "amqp", "mqtt"}:
        return normalized
    raise CliUserError(
        message=f"Unsupported mode value: {value}",
        code="message_invalid_args",
        exit_code=2,
    )


def _outcome_to_dict(outcome: Any) -> dict[str, Any]:
    if hasattr(outcome, "to_dict"):
        return dict(outcome.to_dict())
    if isinstance(outcome, dict):
        return dict(outcome)
    return {"state": "FAILED", "detail": str(outcome)}
