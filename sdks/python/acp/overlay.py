# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .agent import Agent
from .messages import SendResult


class OverlayAdapterError(RuntimeError):
    pass


BusinessHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
PassThroughHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


def is_acp_http_message(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    envelope = body.get("envelope")
    protected = body.get("protected")
    return isinstance(envelope, dict) and isinstance(protected, dict)


@dataclass(frozen=True)
class OverlayTarget:
    agent_id: str
    base_url: str
    well_known_url: str
    identity_document_url: str


@dataclass
class OverlayInboundAdapter:
    agent: Agent
    business_handler: BusinessHandler
    passthrough_handler: PassThroughHandler | None = None

    def handle_request(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise OverlayAdapterError("Overlay inbound adapter requires a JSON object request body")
        if not is_acp_http_message(body):
            if self.passthrough_handler is None:
                raise OverlayAdapterError("Request is not an ACP message and no passthrough_handler is configured")
            payload = self.passthrough_handler(body)
            return {
                "mode": "passthrough",
                "payload": payload if isinstance(payload, dict) else None,
            }
        acp_result = self.agent.handle_incoming(
            body,
            handler=lambda payload, _envelope: self.business_handler(payload),
        )
        return {
            "mode": "acp",
            "acp_result": acp_result,
            "state": acp_result.get("state"),
            "reason_code": acp_result.get("reason_code"),
            "detail": acp_result.get("detail"),
            "response_message": acp_result.get("response_message"),
        }


@dataclass
class OverlayOutboundAdapter:
    agent: Agent

    def resolve_target(
        self,
        *,
        target_base_url: str,
        expected_agent_id: str | None = None,
    ) -> OverlayTarget:
        resolved = self.agent.discovery.resolve_well_known(
            target_base_url,
            expected_agent_id=expected_agent_id,
        )
        well_known = resolved["well_known"]
        identity_document = resolved["identity_document"]
        agent_id = identity_document.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise OverlayAdapterError("Resolved well-known metadata did not include a valid identity_document.agent_id")
        identity_document_url = well_known.get("identity_document")
        if not isinstance(identity_document_url, str) or not identity_document_url.strip():
            raise OverlayAdapterError("Resolved well-known metadata did not include a valid identity_document URL")
        return OverlayTarget(
            agent_id=agent_id,
            base_url=target_base_url.rstrip("/"),
            well_known_url=resolved["well_known_url"],
            identity_document_url=identity_document_url,
        )

    def send_business_payload(
        self,
        *,
        payload: dict[str, Any],
        target_base_url: str | None = None,
        recipient_agent_id: str | None = None,
        context: str | None = None,
        delivery_mode: str = "auto",
        expires_in_seconds: int = 300,
    ) -> tuple[OverlayTarget | None, SendResult]:
        resolved_target: OverlayTarget | None = None
        resolved_recipient = recipient_agent_id
        if target_base_url:
            resolved_target = self.resolve_target(
                target_base_url=target_base_url,
                expected_agent_id=recipient_agent_id,
            )
            if resolved_recipient is None:
                resolved_recipient = resolved_target.agent_id
        if not isinstance(resolved_recipient, str) or not resolved_recipient.strip():
            raise OverlayAdapterError(
                "send_business_payload requires recipient_agent_id or target_base_url for well-known bootstrap",
            )
        send_result = self.agent.send(
            recipients=[resolved_recipient],
            payload=payload,
            context=context,
            delivery_mode=delivery_mode,
            expires_in_seconds=expires_in_seconds,
        )
        return resolved_target, send_result
