"""ACP Mojo bridge over ACP Python SDK.

This module is intentionally thin: it exposes stable helper functions that can be called
from Mojo via Python interop while keeping ACP protocol logic in the Python SDK.
"""

from __future__ import annotations

from typing import Any

import acp


def _normalize_options(options: dict[str, Any] | None) -> dict[str, Any]:
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise TypeError("options must be a dictionary when provided")
    return dict(options)


def load_or_create_agent(agent_id: str, options: dict[str, Any] | None = None) -> acp.Agent:
    normalized = _normalize_options(options)
    return acp.Agent.load_or_create(agent_id, **normalized)


def send(
    agent: acp.Agent,
    recipients: list[str],
    payload: dict[str, Any],
    context: str | None = None,
    message_class: str = "SEND",
    expires_in_seconds: int = 300,
    correlation_id: str | None = None,
    in_reply_to: str | None = None,
    delivery_mode: str | None = None,
) -> Any:
    return agent.send(
        recipients=recipients,
        payload=payload,
        context=context,
        message_class=message_class,
        expires_in_seconds=expires_in_seconds,
        correlation_id=correlation_id,
        in_reply_to=in_reply_to,
        delivery_mode=delivery_mode,
    )


def send_basic(
    agent: acp.Agent,
    recipients: list[str],
    payload: dict[str, Any],
    context: str | None = None,
) -> Any:
    return agent.send_basic(recipients=recipients, payload=payload, context=context)


def receive(
    agent: acp.Agent,
    raw_message: dict[str, Any],
    handler: Any = None,
) -> Any:
    return agent.receive(raw_message=raw_message, handler=handler)


def request_capabilities(agent: acp.Agent, recipient: str) -> Any:
    return agent.request_capabilities(recipient=recipient)


def build_well_known_document(
    agent: acp.Agent,
    base_url: str | None = None,
    identity_document_url: str | None = None,
) -> dict[str, Any]:
    return agent.build_well_known_document(
        base_url=base_url,
        identity_document_url=identity_document_url,
    )


def resolve_well_known(
    agent: acp.Agent,
    base_url: str,
    expected_agent_id: str | None = None,
) -> dict[str, Any]:
    return agent.resolve_well_known(base_url=base_url, expected_agent_id=expected_agent_id)


def register_identity_document(agent: acp.Agent, identity_document: dict[str, Any]) -> None:
    agent.register_identity_document(identity_document)


def create_overlay_runtime(
    agent: acp.Agent,
    base_url: str,
    business_handler: Any,
    passthrough_handler: Any = None,
) -> acp.OverlayFrameworkRuntime:
    return acp.OverlayFrameworkRuntime(
        agent=agent,
        base_url=base_url,
        business_handler=business_handler,
        passthrough_handler=passthrough_handler,
    )


def create_overlay_client(agent: acp.Agent) -> acp.OverlayClient:
    return acp.OverlayClient(agent)


def overlay_send_acp(
    overlay_client: acp.OverlayClient,
    target_url: str,
    payload: dict[str, Any],
    recipient_agent_id: str | None = None,
    context: str | None = None,
    delivery_mode: str = "auto",
    expires_in_seconds: int = 300,
) -> dict[str, Any]:
    return overlay_client.send_acp(
        target_url=target_url,
        payload=payload,
        recipient_agent_id=recipient_agent_id,
        context=context,
        delivery_mode=delivery_mode,
        expires_in_seconds=expires_in_seconds,
    )


def is_acp_http_message(payload: dict[str, Any]) -> bool:
    return acp.is_acp_http_message(payload)

