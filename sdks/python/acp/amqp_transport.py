# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from collections.abc import Callable
import json
import re
import ssl
from typing import Any
from urllib.parse import urlparse

try:
    import pika
    from pika.adapters.blocking_connection import BlockingChannel
except Exception:  # noqa: BLE001
    pika = None  # type: ignore[assignment]
    BlockingChannel = Any  # type: ignore[misc,assignment]

from .transport_auth import AuthConfig, TransportAuthError, auth_config_from_value


DEFAULT_AMQP_EXCHANGE = "acp.exchange"
DEFAULT_AMQP_EXCHANGE_TYPE = "direct"

_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
_AMQP_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


class AMQPTransportError(RuntimeError):
    pass


_AMQP_AUTH_TYPES = {"none", "username_password", "mtls", "custom"}


def _normalize_amqp_auth(value: AuthConfig | dict[str, Any] | None) -> AuthConfig | None:
    try:
        parsed = auth_config_from_value(value)
    except TransportAuthError as exc:
        raise AMQPTransportError(str(exc)) from exc
    if parsed is None:
        return None
    auth_type = parsed.normalized_type()
    if auth_type not in _AMQP_AUTH_TYPES:
        raise AMQPTransportError(f"Auth type '{auth_type}' is not supported for AMQP transport")
    return AuthConfig(type=auth_type, parameters=parsed.normalized_parameters())


def _require_parameter(parameters: dict[str, str], *, key: str, context: str) -> str:
    value = parameters.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AMQPTransportError(f"{context} requires auth.parameters.{key}")
    return value.strip()


def _auth_to_dict(auth: AuthConfig | None) -> dict[str, Any] | None:
    if auth is None:
        return None
    return {
        "type": auth.normalized_type(),
        "parameters": auth.normalized_parameters(),
    }


def _service_auth(amqp_service: dict[str, Any] | None) -> AuthConfig | None:
    if not isinstance(amqp_service, dict):
        return None
    return _normalize_amqp_auth(amqp_service.get("auth"))


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


def queue_name_for_agent(agent_id: str) -> str:
    return f"acp.agent.{agent_identifier_token(agent_id)}"


def routing_key_for_agent(agent_id: str) -> str:
    return f"agent.{agent_identifier_token(agent_id)}"


def build_amqp_service_hint(
    *,
    agent_id: str,
    broker_url: str,
    exchange: str = DEFAULT_AMQP_EXCHANGE,
    auth: AuthConfig | dict[str, Any] | None = None,
) -> dict[str, Any]:
    hint: dict[str, Any] = {
        "broker_url": broker_url,
        "exchange": exchange,
        "queue": queue_name_for_agent(agent_id),
        "routing_key": routing_key_for_agent(agent_id),
    }
    auth_dict = _auth_to_dict(_normalize_amqp_auth(auth))
    if auth_dict is not None:
        hint["auth"] = auth_dict
    return hint


class AMQPTransport:
    def __init__(
        self,
        *,
        broker_url: str,
        exchange: str = DEFAULT_AMQP_EXCHANGE,
        exchange_type: str = DEFAULT_AMQP_EXCHANGE_TYPE,
        auth: AuthConfig | dict[str, Any] | None = None,
    ) -> None:
        if pika is None:
            raise AMQPTransportError(
                "AMQP transport requires the 'pika' package. Install with: pip install pika",
            )
        self.broker_url = broker_url
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.auth = _normalize_amqp_auth(auth)

    def _connection(self, *, broker_url: str, auth: AuthConfig | None) -> Any:
        params = pika.URLParameters(broker_url)
        active_auth = auth or self.auth
        if active_auth is not None:
            auth_type = active_auth.normalized_type()
            parameters = active_auth.normalized_parameters()
            if auth_type in {"username_password", "custom"}:
                username = parameters.get("username")
                password = parameters.get("password")
                if isinstance(username, str) and username.strip():
                    params.credentials = pika.PlainCredentials(username.strip(), (password or "").strip())
                elif auth_type == "username_password":
                    raise AMQPTransportError(
                        "username_password auth requires auth.parameters.username and auth.parameters.password",
                    )
            if auth_type in {"mtls", "custom"}:
                cert_path = parameters.get("cert_path")
                key_path = parameters.get("key_path")
                if cert_path and key_path:
                    parsed = urlparse(broker_url)
                    server_hostname = parsed.hostname or ""
                    context = ssl.create_default_context(
                        cafile=parameters.get("ca_path") if parameters.get("ca_path") else None,
                    )
                    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
                    params.ssl_options = pika.SSLOptions(context, server_hostname=server_hostname)
                elif auth_type == "mtls":
                    raise AMQPTransportError(
                        "mtls auth requires auth.parameters.cert_path and auth.parameters.key_path",
                    )
        try:
            return pika.BlockingConnection(params)
        except Exception as exc:  # noqa: BLE001
            raise AMQPTransportError(f"Failed to connect to AMQP broker {broker_url}: {exc}") from exc

    def _declare_route(
        self,
        channel: BlockingChannel,
        *,
        exchange: str,
        queue_name: str | None,
        routing_key: str,
    ) -> None:
        channel.exchange_declare(exchange=exchange, exchange_type=self.exchange_type, durable=True)
        if queue_name:
            channel.queue_declare(queue=queue_name, durable=True)
            channel.queue_bind(queue=queue_name, exchange=exchange, routing_key=routing_key)

    def publish(
        self,
        *,
        message: dict[str, Any],
        recipient_agent_id: str,
        amqp_service: dict[str, Any] | None = None,
    ) -> None:
        exchange = (
            str(amqp_service.get("exchange"))
            if isinstance(amqp_service, dict) and amqp_service.get("exchange")
            else self.exchange
        )
        queue_name = (
            str(amqp_service.get("queue"))
            if isinstance(amqp_service, dict) and amqp_service.get("queue")
            else queue_name_for_agent(recipient_agent_id)
        )
        routing_key = (
            str(amqp_service.get("routing_key"))
            if isinstance(amqp_service, dict) and amqp_service.get("routing_key")
            else routing_key_for_agent(recipient_agent_id)
        )
        headers = self._metadata_headers(message)
        broker_url = (
            str(amqp_service.get("broker_url"))
            if isinstance(amqp_service, dict) and amqp_service.get("broker_url")
            else self.broker_url
        )
        auth = _service_auth(amqp_service)

        connection = self._connection(broker_url=broker_url, auth=auth)
        try:
            channel = connection.channel()
            self._declare_route(
                channel,
                exchange=exchange,
                queue_name=queue_name,
                routing_key=routing_key,
            )
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
            raise AMQPTransportError(
                f"Failed to publish ACP message to AMQP recipient {recipient_agent_id}: {exc}",
            ) from exc
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    def consume(
        self,
        *,
        agent_id: str,
        handler: Callable[[dict[str, Any]], bool],
        amqp_service: dict[str, Any] | None = None,
        max_messages: int | None = None,
    ) -> int:
        exchange = (
            str(amqp_service.get("exchange"))
            if isinstance(amqp_service, dict) and amqp_service.get("exchange")
            else self.exchange
        )
        queue_name = (
            str(amqp_service.get("queue"))
            if isinstance(amqp_service, dict) and amqp_service.get("queue")
            else queue_name_for_agent(agent_id)
        )
        routing_key = (
            str(amqp_service.get("routing_key"))
            if isinstance(amqp_service, dict) and amqp_service.get("routing_key")
            else routing_key_for_agent(agent_id)
        )
        broker_url = (
            str(amqp_service.get("broker_url"))
            if isinstance(amqp_service, dict) and amqp_service.get("broker_url")
            else self.broker_url
        )
        auth = _service_auth(amqp_service)

        processed = 0
        connection = self._connection(broker_url=broker_url, auth=auth)
        try:
            channel = connection.channel()
            self._declare_route(
                channel,
                exchange=exchange,
                queue_name=queue_name,
                routing_key=routing_key,
            )
            while max_messages is None or processed < max_messages:
                method_frame, _, body = channel.basic_get(queue=queue_name, auto_ack=False)
                if method_frame is None:
                    break
                try:
                    message = json.loads(body.decode("utf-8"))
                    if not isinstance(message, dict):
                        raise ValueError("ACP AMQP message must decode to a JSON object")
                    should_ack = bool(handler(message))
                except Exception:  # noqa: BLE001
                    should_ack = False

                if should_ack:
                    channel.basic_ack(method_frame.delivery_tag)
                else:
                    channel.basic_nack(method_frame.delivery_tag, requeue=True)
                processed += 1
        except Exception as exc:  # noqa: BLE001
            raise AMQPTransportError(f"Failed consuming AMQP queue for {agent_id}: {exc}") from exc
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass
        return processed

    @staticmethod
    def _metadata_headers(message: dict[str, Any]) -> dict[str, str]:
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
