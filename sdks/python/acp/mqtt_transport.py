# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from collections.abc import Callable
import json
from queue import Empty, Queue
import re
from typing import Any
from urllib.parse import urlparse

try:
    import paho.mqtt.client as mqtt
except Exception:  # noqa: BLE001
    mqtt = None  # type: ignore[assignment]


DEFAULT_MQTT_QOS = 1
DEFAULT_MQTT_TOPIC_PREFIX = "acp/agent"

_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
_MQTT_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


class MQTTTransportError(RuntimeError):
    pass


def _parse_agent_id(agent_id: str) -> tuple[str, str | None]:
    match = _AGENT_ID_PATTERN.match(agent_id)
    if match is None:
        raise ValueError(f"Invalid agent identifier: {agent_id}")
    return match.group("name"), match.group("domain")


def agent_identifier_token(agent_id: str) -> str:
    name, domain = _parse_agent_id(agent_id)
    token = name if not domain else f"{name}.{domain}"
    token = _MQTT_TOKEN_PATTERN.sub(".", token.strip("."))
    token = re.sub(r"\.+", ".", token).strip(".").lower()
    return token or "unknown"


def topic_for_agent(
    agent_id: str,
    *,
    topic_prefix: str = DEFAULT_MQTT_TOPIC_PREFIX,
) -> str:
    prefix = topic_prefix.rstrip("/")
    return f"{prefix}/{agent_identifier_token(agent_id)}"


def build_mqtt_service_hint(
    *,
    agent_id: str,
    broker_url: str,
    topic: str | None = None,
    qos: int = DEFAULT_MQTT_QOS,
    topic_prefix: str = DEFAULT_MQTT_TOPIC_PREFIX,
) -> dict[str, Any]:
    return {
        "broker_url": broker_url,
        "topic": topic if isinstance(topic, str) and topic.strip() else topic_for_agent(
            agent_id,
            topic_prefix=topic_prefix,
        ),
        "qos": _coerce_qos(qos),
    }


def _coerce_qos(value: Any) -> int:
    try:
        qos = int(value)
    except Exception:  # noqa: BLE001
        qos = DEFAULT_MQTT_QOS
    if qos not in {0, 1, 2}:
        return DEFAULT_MQTT_QOS
    return qos


class MQTTTransport:
    def __init__(
        self,
        *,
        broker_url: str,
        qos: int = DEFAULT_MQTT_QOS,
        topic_prefix: str = DEFAULT_MQTT_TOPIC_PREFIX,
        keepalive_seconds: int = 30,
    ) -> None:
        if mqtt is None:
            raise MQTTTransportError(
                "MQTT transport requires the 'paho-mqtt' package. Install with: pip install paho-mqtt",
            )
        self.broker_url = broker_url
        self.qos = _coerce_qos(qos)
        self.topic_prefix = topic_prefix
        self.keepalive_seconds = max(5, int(keepalive_seconds))

    @staticmethod
    def _metadata_properties(message: dict[str, Any]) -> dict[str, str]:
        envelope = message.get("envelope") if isinstance(message, dict) else None
        if not isinstance(envelope, dict):
            return {}
        properties: dict[str, str] = {}
        for src, dest in (
            ("acp_version", "acp_version"),
            ("message_class", "acp_message_class"),
            ("message_id", "acp_message_id"),
            ("operation_id", "acp_operation_id"),
            ("sender", "acp_sender"),
        ):
            value = envelope.get(src)
            if isinstance(value, str):
                properties[dest] = value
        return properties

    def _resolve_target(
        self,
        *,
        recipient_agent_id: str,
        mqtt_service: dict[str, Any] | None,
    ) -> tuple[str, str, int]:
        broker_url = (
            str(mqtt_service.get("broker_url"))
            if isinstance(mqtt_service, dict) and mqtt_service.get("broker_url")
            else self.broker_url
        )
        topic = (
            str(mqtt_service.get("topic"))
            if isinstance(mqtt_service, dict) and mqtt_service.get("topic")
            else topic_for_agent(recipient_agent_id, topic_prefix=self.topic_prefix)
        )
        qos = (
            _coerce_qos(mqtt_service.get("qos"))
            if isinstance(mqtt_service, dict)
            else self.qos
        )
        return broker_url, topic, qos

    def _connect_client(
        self,
        *,
        broker_url: str,
        on_message: Callable[..., Any] | None = None,
    ) -> Any:
        parsed = urlparse(broker_url)
        host = parsed.hostname
        if not host:
            raise MQTTTransportError(f"Invalid MQTT broker_url: {broker_url}")
        scheme = (parsed.scheme or "mqtt").lower()
        port = parsed.port or (8883 if scheme in {"mqtts", "ssl", "wss"} else 1883)

        protocol = getattr(mqtt, "MQTTv5", mqtt.MQTTv311)
        try:
            callback_api = getattr(mqtt, "CallbackAPIVersion", None)
            if callback_api is not None:
                client = mqtt.Client(callback_api.VERSION2, protocol=protocol)
            else:
                client = mqtt.Client(protocol=protocol)
        except Exception:  # noqa: BLE001
            client = mqtt.Client(protocol=getattr(mqtt, "MQTTv311", 4))

        if parsed.username:
            client.username_pw_set(parsed.username, parsed.password)
        if scheme in {"mqtts", "ssl", "wss"}:
            try:
                client.tls_set()
            except Exception:  # noqa: BLE001
                pass
        if on_message is not None:
            client.on_message = on_message
        try:
            client.connect(host, port, self.keepalive_seconds)
        except Exception as exc:  # noqa: BLE001
            raise MQTTTransportError(
                f"Failed to connect to MQTT broker {broker_url}: {exc}",
            ) from exc
        return client

    @staticmethod
    def _mqtt_user_properties(properties: dict[str, str]) -> Any:
        if mqtt is None:
            return None
        packettypes = getattr(mqtt, "PacketTypes", None)
        properties_cls = getattr(mqtt, "Properties", None)
        if packettypes is None or properties_cls is None:
            return None
        try:
            mqtt_properties = properties_cls(packettypes.PUBLISH)
            mqtt_properties.UserProperty = list(properties.items())
            return mqtt_properties
        except Exception:  # noqa: BLE001
            return None

    def publish(
        self,
        *,
        message: dict[str, Any],
        recipient_agent_id: str,
        mqtt_service: dict[str, Any] | None = None,
    ) -> None:
        broker_url, topic, qos = self._resolve_target(
            recipient_agent_id=recipient_agent_id,
            mqtt_service=mqtt_service,
        )
        payload = json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")
        properties = self._metadata_properties(message)
        client = self._connect_client(broker_url=broker_url)
        try:
            publish_kwargs: dict[str, Any] = {"qos": qos, "retain": False}
            mqtt_properties = self._mqtt_user_properties(properties)
            if mqtt_properties is not None:
                publish_kwargs["properties"] = mqtt_properties
            info = client.publish(topic, payload, **publish_kwargs)
            if hasattr(info, "wait_for_publish"):
                info.wait_for_publish()
        except Exception as exc:  # noqa: BLE001
            raise MQTTTransportError(
                f"Failed to publish ACP message to MQTT recipient {recipient_agent_id}: {exc}",
            ) from exc
        finally:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _enable_manual_ack(client: Any) -> bool:
        manual_ack_set = getattr(client, "manual_ack_set", None)
        if callable(manual_ack_set):
            try:
                manual_ack_set(True)
                return callable(getattr(client, "ack", None))
            except Exception:  # noqa: BLE001
                return False
        return False

    def consume(
        self,
        *,
        agent_id: str,
        handler: Callable[[dict[str, Any]], bool],
        mqtt_service: dict[str, Any] | None = None,
        max_messages: int | None = None,
        poll_timeout_seconds: float = 1.0,
    ) -> int:
        broker_url, topic, qos = self._resolve_target(
            recipient_agent_id=agent_id,
            mqtt_service=mqtt_service,
        )
        queue: Queue[Any] = Queue()

        def _on_message(client: Any, userdata: Any, msg: Any, *args: Any) -> None:  # noqa: ARG001
            queue.put(msg)

        processed = 0
        client = self._connect_client(broker_url=broker_url, on_message=_on_message)
        manual_ack = self._enable_manual_ack(client)
        try:
            client.subscribe(topic, qos=qos)
            client.loop_start()
            while max_messages is None or processed < max_messages:
                try:
                    mqtt_message = queue.get(timeout=poll_timeout_seconds)
                except Empty:
                    break

                should_ack = False
                try:
                    payload = json.loads(bytes(mqtt_message.payload).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("ACP MQTT message must decode to a JSON object")
                    should_ack = bool(handler(payload))
                except Exception:  # noqa: BLE001
                    should_ack = False

                if manual_ack:
                    if should_ack:
                        client.ack(mqtt_message.mid, mqtt_message.qos)
                    else:
                        # Keep message unacked so broker can redeliver under QoS 1 semantics.
                        processed += 1
                        continue
                processed += 1
        except Exception as exc:  # noqa: BLE001
            raise MQTTTransportError(f"Failed consuming MQTT topic for {agent_id}: {exc}") from exc
        finally:
            try:
                client.loop_stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        return processed
