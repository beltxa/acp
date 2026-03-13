from __future__ import annotations

from collections.abc import Callable
import json
import re
from typing import Any

try:
    import pika
    from pika.adapters.blocking_connection import BlockingChannel
except Exception:  # noqa: BLE001
    pika = None  # type: ignore[assignment]
    BlockingChannel = Any  # type: ignore[misc,assignment]


DEFAULT_AMQP_EXCHANGE = "acp.exchange"
DEFAULT_AMQP_EXCHANGE_TYPE = "direct"

_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
_AMQP_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


class AMQPTransportError(RuntimeError):
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


def queue_name_for_agent(agent_id: str) -> str:
    return f"acp.agent.{agent_identifier_token(agent_id)}"


def routing_key_for_agent(agent_id: str) -> str:
    return f"agent.{agent_identifier_token(agent_id)}"


def build_amqp_service_hint(
    *,
    agent_id: str,
    broker_url: str,
    exchange: str = DEFAULT_AMQP_EXCHANGE,
) -> dict[str, str]:
    return {
        "broker_url": broker_url,
        "exchange": exchange,
        "queue": queue_name_for_agent(agent_id),
        "routing_key": routing_key_for_agent(agent_id),
    }


class AMQPTransport:
    def __init__(
        self,
        *,
        broker_url: str,
        exchange: str = DEFAULT_AMQP_EXCHANGE,
        exchange_type: str = DEFAULT_AMQP_EXCHANGE_TYPE,
    ) -> None:
        if pika is None:
            raise AMQPTransportError(
                "AMQP transport requires the 'pika' package. Install with: pip install pika",
            )
        self.broker_url = broker_url
        self.exchange = exchange
        self.exchange_type = exchange_type

    def _connection(self) -> Any:
        try:
            return pika.BlockingConnection(pika.URLParameters(self.broker_url))
        except Exception as exc:  # noqa: BLE001
            raise AMQPTransportError(f"Failed to connect to AMQP broker {self.broker_url}: {exc}") from exc

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

        connection = self._connection()
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

        processed = 0
        connection = self._connection()
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
                    channel.basic_nack(method_frame.delivery_tag, requeue=False)
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
