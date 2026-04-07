# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import json
import re
from typing import Any

try:
    import pika
except Exception:  # noqa: BLE001
    pika = None  # type: ignore[assignment]


DEFAULT_AMQP_EXCHANGE = "acp.exchange"
DEFAULT_AMQP_EXCHANGE_TYPE = "direct"

_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
_AMQP_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


class AmqpRelayError(RuntimeError):
    pass


def _parse_agent_id(agent_id: str) -> tuple[str, str | None]:
    match = _AGENT_ID_PATTERN.match(agent_id)
    if match is None:
        raise ValueError(f"Invalid agent identifier: {agent_id}")
    return match.group("name"), match.group("domain")


def agent_identifier_token(agent_id: str) -> str:
    name, domain = _parse_agent_id(agent_id)
    token = name if not domain else f"{name}.{domain}"
    token = _AMQP_TOKEN_PATTERN.sub(".", token.strip("."))
    token = re.sub(r"\.+", ".", token).strip(".")
    return token or "unknown"


def _namespace_token(namespace: str | None) -> str | None:
    if not isinstance(namespace, str) or not namespace.strip():
        return None
    token = _AMQP_TOKEN_PATTERN.sub(".", namespace.strip("."))
    token = re.sub(r"\.+", ".", token).strip(".")
    return token or None


def queue_name_for_agent(agent_id: str, namespace: str | None = None) -> str:
    base = f"acp.agent.{agent_identifier_token(agent_id)}"
    namespace_token = _namespace_token(namespace)
    if namespace_token is None:
        return base
    return f"{base}.namespace.{namespace_token}"


def routing_key_for_agent(agent_id: str, namespace: str | None = None) -> str:
    base = f"agent.{agent_identifier_token(agent_id)}"
    namespace_token = _namespace_token(namespace)
    if namespace_token is None:
        return base
    return f"{base}.namespace.{namespace_token}"


def metadata_headers(message: dict[str, Any]) -> dict[str, str]:
    envelope = message.get("envelope") if isinstance(message, dict) else None
    if not isinstance(envelope, dict):
        return {}
    headers: dict[str, str] = {}
    for src, dest in (
        ("acp_version", "acp_version"),
        ("message_class", "acp_message_class"),
        ("message_id", "acp_message_id"),
        ("operation_id", "acp_operation_id"),
        ("sender", "acp_sender"),
    ):
        value = envelope.get(src)
        if isinstance(value, str):
            headers[dest] = value
    return headers


class RelayAmqpPublisher:
    def __init__(
        self,
        *,
        default_broker_url: str | None = None,
        default_exchange: str = DEFAULT_AMQP_EXCHANGE,
        exchange_type: str = DEFAULT_AMQP_EXCHANGE_TYPE,
    ) -> None:
        self.default_broker_url = default_broker_url
        self.default_exchange = default_exchange
        self.exchange_type = exchange_type

    def publish(
        self,
        *,
        message: dict[str, Any],
        recipient: str,
        amqp_service: dict[str, Any],
    ) -> None:
        if pika is None:
            raise AmqpRelayError("AMQP relay delivery requires the 'pika' package")

        broker_url = self._pick(amqp_service, "broker_url", self.default_broker_url)
        if not broker_url:
            raise AmqpRelayError("AMQP broker_url missing for recipient")

        envelope = message.get("envelope") if isinstance(message, dict) else None
        namespace = envelope.get("namespace") if isinstance(envelope, dict) else None
        namespace_value = namespace if isinstance(namespace, str) and namespace.strip() else None

        exchange = self._pick(amqp_service, "exchange", self.default_exchange)
        queue_name = self._pick(amqp_service, "queue", queue_name_for_agent(recipient, namespace_value))
        routing_key = self._pick(
            amqp_service,
            "routing_key",
            routing_key_for_agent(recipient, namespace_value),
        )
        headers = metadata_headers(message)

        try:
            connection = pika.BlockingConnection(pika.URLParameters(broker_url))
        except Exception as exc:  # noqa: BLE001
            raise AmqpRelayError(f"Failed to connect to AMQP broker {broker_url}: {exc}") from exc

        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=exchange, exchange_type=self.exchange_type, durable=True)
            if queue_name:
                channel.queue_declare(queue=queue_name, durable=True)
                channel.queue_bind(queue=queue_name, exchange=exchange, routing_key=routing_key)
            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(message, sort_keys=True, separators=(",", ":")),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    headers=headers,
                ),
                mandatory=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise AmqpRelayError(
                f"Failed to publish ACP message to AMQP recipient {recipient}: {exc}",
            ) from exc
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _pick(service: dict[str, Any], key: str, fallback: str | None) -> str | None:
        value = service.get(key) if isinstance(service, dict) else None
        if isinstance(value, str) and value.strip():
            return value
        return fallback
