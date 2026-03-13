from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import requests

from amqp_binding import AmqpRelayError, RelayAmqpPublisher
from storage import MessageStore


_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _parse_agent_id(agent_id: str) -> tuple[str, str | None]:
    match = _AGENT_ID_PATTERN.match(agent_id)
    if match is None:
        raise ValueError(f"Invalid agent identifier: {agent_id}")
    return match.group("name"), match.group("domain")


def _is_identity_document(value: dict[str, Any]) -> bool:
    required = ("agent_id", "keys", "service", "valid_until")
    return all(key in value for key in required)


@dataclass
class RelayRoutingConfig:
    default_scheme: str = "https"
    timeout_seconds: int = 5
    relay_hints: list[str] | None = None
    store_and_forward: bool = True
    max_retry_attempts: int = 3
    retry_backoff_seconds: float = 2.0
    amqp_broker_url: str | None = None
    amqp_exchange: str = "acp.exchange"
    amqp_exchange_type: str = "direct"


class RelayDiscoveryResolver:
    def __init__(self, config: RelayRoutingConfig) -> None:
        self.config = config
        self.cache: dict[str, dict[str, Any]] = {}
        self.registry: dict[str, dict[str, Any]] = {}

    def register_identity_document(self, identity_document: dict[str, Any]) -> None:
        if not _is_identity_document(identity_document):
            raise ValueError("Invalid identity document")
        agent_id = identity_document["agent_id"]
        self.registry[agent_id] = identity_document
        self.cache[agent_id] = identity_document

    def _well_known_url(self, agent_id: str) -> str:
        name, domain = _parse_agent_id(agent_id)
        if not domain:
            raise ValueError(f"Agent id {agent_id} has no domain")
        return f"{self.config.default_scheme}://{domain}/.well-known/acp/agents/{name}"

    def _fetch_well_known(self, agent_id: str) -> dict[str, Any] | None:
        try:
            url = self._well_known_url(agent_id)
        except ValueError:
            return None
        try:
            response = requests.get(url, timeout=self.config.timeout_seconds)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            value = response.json()
        except ValueError:
            return None
        if not isinstance(value, dict) or not _is_identity_document(value):
            return None
        return value

    def _fetch_via_hints(self, agent_id: str) -> dict[str, Any] | None:
        for relay_hint in self.config.relay_hints or []:
            url = f"{relay_hint.rstrip('/')}/discover"
            try:
                response = requests.get(
                    url,
                    params={"agent_id": agent_id},
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException:
                continue
            if response.status_code != 200:
                continue
            try:
                value = response.json()
            except ValueError:
                continue
            if isinstance(value, dict) and "identity_document" in value:
                value = value["identity_document"]
            if not isinstance(value, dict) or not _is_identity_document(value):
                continue
            return value
        return None

    def resolve(self, agent_id: str) -> dict[str, Any]:
        if agent_id in self.registry:
            return self.registry[agent_id]
        if agent_id in self.cache:
            return self.cache[agent_id]

        identity_document = self._fetch_well_known(agent_id)
        if identity_document is None:
            identity_document = self._fetch_via_hints(agent_id)
        if identity_document is None:
            raise LookupError(f"Unable to resolve recipient identity for {agent_id}")

        self.cache[agent_id] = identity_document
        return identity_document


class RelayRouter:
    def __init__(
        self,
        resolver: RelayDiscoveryResolver,
        *,
        timeout_seconds: int = 10,
        store: MessageStore | None = None,
        store_and_forward: bool = True,
        max_retry_attempts: int = 3,
        retry_backoff_seconds: float = 2.0,
        amqp_publisher: RelayAmqpPublisher | None = None,
        amqp_broker_url: str | None = None,
        amqp_exchange: str = "acp.exchange",
        amqp_exchange_type: str = "direct",
    ) -> None:
        self.resolver = resolver
        self.timeout_seconds = timeout_seconds
        self.store = store
        self.store_and_forward = store_and_forward
        self.max_retry_attempts = max_retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.amqp_publisher = amqp_publisher or RelayAmqpPublisher(
            default_broker_url=amqp_broker_url,
            default_exchange=amqp_exchange,
            exchange_type=amqp_exchange_type,
        )

    def _state_from_response(
        self,
        *,
        status_code: int,
        response_class: str | None,
        reason_code: str | None,
    ) -> str:
        if 200 <= status_code < 300:
            if response_class == "FAIL":
                if reason_code == "EXPIRED_MESSAGE":
                    return "EXPIRED"
                if reason_code == "POLICY_REJECTED":
                    return "DECLINED"
                return "FAILED"
            if response_class in {"ACK", "CAPABILITIES"}:
                return "ACKNOWLEDGED"
            return "DELIVERED"
        if status_code == 410:
            return "EXPIRED"
        if status_code in {401, 403, 409, 422}:
            return "DECLINED"
        return "FAILED"

    def _public_outcome(self, outcome: dict[str, Any]) -> dict[str, Any]:
        public = dict(outcome)
        public.pop("retriable", None)
        return public

    def _deliver_to_endpoint(
        self,
        *,
        recipient: str,
        endpoint: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {"recipient": recipient, "state": "FAILED", "retriable": False}
        try:
            response = requests.post(endpoint, json=message, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            outcome["detail"] = f"Delivery transport error: {exc}"
            outcome["reason_code"] = "POLICY_REJECTED"
            outcome["retriable"] = True
            return outcome

        outcome["status_code"] = response.status_code
        body: dict[str, Any] | None = None
        try:
            body = response.json()
        except ValueError:
            body = None

        response_message = body.get("response_message") if isinstance(body, dict) else None
        if isinstance(response_message, dict):
            outcome["response_message"] = response_message
            response_class = response_message.get("envelope", {}).get("message_class")
            if isinstance(response_class, str):
                outcome["response_class"] = response_class

        if isinstance(body, dict):
            reason_code = body.get("reason_code")
            detail = body.get("detail")
            if isinstance(reason_code, str):
                outcome["reason_code"] = reason_code
            if isinstance(detail, str):
                outcome["detail"] = detail
            if isinstance(body.get("retriable"), bool):
                outcome["retriable"] = body["retriable"]

        reason_code = outcome.get("reason_code")
        response_class = outcome.get("response_class")
        outcome["state"] = self._state_from_response(
            status_code=response.status_code,
            response_class=response_class if isinstance(response_class, str) else None,
            reason_code=reason_code if isinstance(reason_code, str) else None,
        )

        if outcome["state"] not in {"DECLINED", "EXPIRED"} and response.status_code in _RETRYABLE_STATUS_CODES:
            outcome["retriable"] = True
        if "detail" not in outcome and response.status_code >= 400:
            outcome["detail"] = f"Recipient HTTP {response.status_code}"
        return outcome

    def _queue_retry(
        self,
        *,
        recipient: str,
        endpoint: str,
        message: dict[str, Any],
        outcome: dict[str, Any],
    ) -> None:
        if self.store is None:
            return
        envelope = message.get("envelope", {})
        message_id = str(envelope.get("message_id", ""))
        operation_id = str(envelope.get("operation_id", ""))
        self.store.queue_retry(
            message_id=message_id,
            operation_id=operation_id,
            recipient=recipient,
            endpoint=endpoint,
            message=message,
            reason_code=str(outcome.get("reason_code", "POLICY_REJECTED")),
            detail=str(outcome.get("detail", "Delivery failed")),
            delay_seconds=self.retry_backoff_seconds,
        )

    def _deliver_to_amqp(
        self,
        *,
        recipient: str,
        message: dict[str, Any],
        amqp_service: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            self.amqp_publisher.publish(
                message=message,
                recipient=recipient,
                amqp_service=amqp_service,
            )
        except AmqpRelayError as exc:
            return {
                "recipient": recipient,
                "state": "FAILED",
                "reason_code": "POLICY_REJECTED",
                "detail": str(exc),
            }
        return {
            "recipient": recipient,
            "state": "DELIVERED",
            "transport": "amqp",
        }

    def route_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        envelope = message.get("envelope", {})
        recipients = envelope.get("recipients", [])
        outcomes: list[dict[str, Any]] = []

        for recipient in recipients:
            outcome: dict[str, Any]
            try:
                identity_document = self.resolver.resolve(recipient)
            except LookupError as exc:
                outcome = {
                    "recipient": recipient,
                    "state": "FAILED",
                    "detail": str(exc),
                    "reason_code": "POLICY_REJECTED",
                }
                outcomes.append(outcome)
                continue

            endpoint = identity_document.get("service", {}).get("direct_endpoint")
            amqp_service = identity_document.get("service", {}).get("amqp")
            if not isinstance(endpoint, str) or not endpoint:
                if isinstance(amqp_service, dict):
                    outcomes.append(
                        self._deliver_to_amqp(
                            recipient=recipient,
                            message=message,
                            amqp_service=amqp_service,
                        ),
                    )
                else:
                    outcome = {
                        "recipient": recipient,
                        "state": "FAILED",
                        "detail": "Recipient identity document missing direct_endpoint/amqp",
                        "reason_code": "POLICY_REJECTED",
                    }
                    outcomes.append(outcome)
                continue

            outcome = self._deliver_to_endpoint(
                recipient=recipient,
                endpoint=endpoint,
                message=message,
            )
            if self.store_and_forward and outcome.get("retriable"):
                self._queue_retry(
                    recipient=recipient,
                    endpoint=endpoint,
                    message=message,
                    outcome=outcome,
                )
                queued_outcome = dict(outcome)
                queued_outcome["state"] = "PENDING"
                queued_outcome["queued_for_retry"] = True
                detail = queued_outcome.get("detail")
                if isinstance(detail, str) and detail:
                    queued_outcome["detail"] = f"Queued for retry: {detail}"
                outcomes.append(self._public_outcome(queued_outcome))
                continue

            outcomes.append(self._public_outcome(outcome))

        return outcomes

    def process_pending_deliveries(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if self.store is None:
            return []

        processed: list[dict[str, Any]] = []
        pending_records = self.store.claim_due_retries(limit=limit)
        for record in pending_records:
            recipient = str(record["recipient"])
            endpoint = str(record["endpoint"])
            message = dict(record["message"])
            message_id = str(record["message_id"])
            attempts = int(record.get("attempts", 1))

            outcome = self._deliver_to_endpoint(
                recipient=recipient,
                endpoint=endpoint,
                message=message,
            )
            if (
                self.store_and_forward
                and outcome.get("retriable")
                and attempts < self.max_retry_attempts
            ):
                delay_seconds = self.retry_backoff_seconds * (2 ** (attempts - 1))
                self.store.requeue_retry(
                    record,
                    delay_seconds=delay_seconds,
                    reason_code=str(outcome.get("reason_code", "POLICY_REJECTED")),
                    detail=str(outcome.get("detail", "Delivery failed")),
                )
                pending_outcome = dict(outcome)
                pending_outcome["state"] = "PENDING"
                pending_outcome["queued_for_retry"] = True
                pending_outcome["detail"] = (
                    f"Retry pending after attempt {attempts}: "
                    f"{pending_outcome.get('detail', 'delivery failed')}"
                )
                public_pending_outcome = self._public_outcome(pending_outcome)
                self.store.update_outcome(message_id=message_id, outcome=public_pending_outcome)
                processed.append(public_pending_outcome)
                continue

            public_outcome = self._public_outcome(outcome)
            self.store.update_outcome(message_id=message_id, outcome=public_outcome)
            processed.append(public_outcome)
        return processed
