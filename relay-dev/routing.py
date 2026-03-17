# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import copy
from dataclasses import dataclass
import logging
import re
from typing import Any
import warnings
from urllib.parse import urljoin, urlparse

import requests

from amqp_binding import AmqpRelayError, RelayAmqpPublisher
from http_security import (
    HttpSecurityError,
    RelayHttpSecurityPolicy,
    enforce_http_security,
    requests_cert_value,
    requests_verify_value,
    security_profile,
    validate_http_security_policy,
)
from identity_security import IdentityVerificationError, verify_message_signature
from storage import MessageStore


_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _parse_agent_id(agent_id: str) -> tuple[str, str | None]:
    match = _AGENT_ID_PATTERN.match(agent_id)
    if match is None:
        raise ValueError(f"Invalid agent identifier: {agent_id}")
    return match.group("name"), match.group("domain")


def _is_valid_identity_reference(reference: str) -> bool:
    normalized = reference.strip()
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.scheme:
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    return normalized.startswith("/")


def _is_valid_http_endpoint(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    ca_file: str | None = None
    mtls_enabled: bool = False
    cert_file: str | None = None
    key_file: str | None = None
    key_provider_info: dict[str, Any] | None = None


class RelayDiscoveryResolver:
    def __init__(self, config: RelayRoutingConfig) -> None:
        self.config = config
        self._logger = logging.getLogger("acp.relay.discovery")
        self.policy = RelayHttpSecurityPolicy(
            allow_insecure_http=config.allow_insecure_http,
            allow_insecure_tls=config.allow_insecure_tls,
            ca_file=config.ca_file,
            mtls_enabled=config.mtls_enabled,
            cert_file=config.cert_file,
            key_file=config.key_file,
        )
        self._warned_messages: set[str] = set()
        try:
            warning_messages = validate_http_security_policy(
                self.policy,
                context="Relay discovery resolver configuration",
            )
        except HttpSecurityError as exc:
            raise LookupError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        self.cache: dict[str, dict[str, Any]] = {}
        self.registry: dict[str, dict[str, Any]] = {}

    def _emit_warning(self, message: str) -> None:
        if message in self._warned_messages:
            return
        self._warned_messages.add(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _verify_for_url(self, url: str, *, context: str) -> tuple[bool | str, tuple[str, str] | None]:
        try:
            warning_messages = enforce_http_security(url, policy=self.policy, context=context)
        except HttpSecurityError as exc:
            raise LookupError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        try:
            cert = requests_cert_value(url, policy=self.policy)
        except HttpSecurityError as exc:
            raise LookupError(str(exc)) from exc
        return requests_verify_value(url, policy=self.policy), cert

    def register_identity_document(self, identity_document: dict[str, Any]) -> None:
        if not _is_identity_document(identity_document):
            raise ValueError("Invalid identity document")
        agent_id = identity_document["agent_id"]
        self.registry[agent_id] = identity_document
        self.cache[agent_id] = identity_document

    def get_registered_identity_document(self, agent_id: str) -> dict[str, Any] | None:
        value = self.registry.get(agent_id)
        if value is None:
            return None
        return copy.deepcopy(value)

    def list_registered_identity_documents(self, *, limit: int = 100) -> list[dict[str, Any]]:
        keys = sorted(self.registry.keys())[:limit]
        return [copy.deepcopy(self.registry[key]) for key in keys]

    def _well_known_url(self, agent_id: str) -> str:
        _, domain = _parse_agent_id(agent_id)
        if not domain:
            raise ValueError(f"Agent id {agent_id} has no domain")
        return f"{self.config.default_scheme}://{domain}/.well-known/acp"

    def _fetch_json(self, *, url: str, context: str, params: dict[str, str] | None = None) -> dict[str, Any] | None:
        verify, cert = self._verify_for_url(url, context=context)
        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.config.timeout_seconds,
                verify=verify,
                cert=cert,
            )
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            value = response.json()
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def _extract_identity_document(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        identity_document = payload.get("identity_document")
        if identity_document is None and "agent_id" in payload:
            identity_document = payload
        return identity_document if isinstance(identity_document, dict) else None

    def _is_valid_well_known(self, payload: dict[str, Any]) -> bool:
        agent_id = payload.get("agent_id")
        transports = payload.get("transports")
        version = payload.get("version")
        identity_reference = payload.get("identity_document")
        security_profile = payload.get("security_profile")
        allowed_profiles = {"http", "https", "mtls", "https+mtls"}
        if security_profile is not None and (
            not isinstance(security_profile, str) or security_profile not in allowed_profiles
        ):
            return False
        if version != "1.0":
            return False
        if not isinstance(transports, dict):
            return False
        for hint in transports.values():
            if not isinstance(hint, dict):
                return False
            endpoint = hint.get("endpoint")
            if endpoint is not None:
                if not isinstance(endpoint, str) or not _is_valid_http_endpoint(endpoint):
                    return False
            hint_profile = hint.get("security_profile")
            if hint_profile is not None and (
                not isinstance(hint_profile, str) or hint_profile not in allowed_profiles
            ):
                return False
        if not isinstance(agent_id, str) or not agent_id.strip():
            return False
        try:
            _parse_agent_id(agent_id)
        except ValueError:
            return False
        return isinstance(identity_reference, str) and _is_valid_identity_reference(identity_reference)

    def _fetch_well_known(self, agent_id: str) -> dict[str, Any] | None:
        try:
            url = self._well_known_url(agent_id)
        except ValueError:
            return None
        payload = self._fetch_json(url=url, context="Relay .well-known lookup")
        if payload is None or not self._is_valid_well_known(payload):
            return None
        if payload.get("agent_id") != agent_id:
            return None
        identity_reference = payload.get("identity_document")
        if not isinstance(identity_reference, str) or not identity_reference.strip():
            return None
        identity_url = identity_reference if "://" in identity_reference else urljoin(url, identity_reference)
        identity_payload = self._fetch_json(
            url=identity_url,
            context="Relay identity document lookup",
        )
        if identity_payload is None:
            return None
        identity_document = self._extract_identity_document(identity_payload)
        if identity_document is None or not _is_identity_document(identity_document):
            return None
        if identity_document.get("agent_id") != agent_id:
            return None
        return identity_document

    def _fetch_via_hints(self, agent_id: str) -> dict[str, Any] | None:
        for relay_hint in self.config.relay_hints or []:
            url = f"{relay_hint.rstrip('/')}/discover"
            value = self._fetch_json(
                url=url,
                params={"agent_id": agent_id},
                context="Relay discovery hint lookup",
            )
            if value is None:
                continue
            identity_document = self._extract_identity_document(value)
            if identity_document is None or not _is_identity_document(identity_document):
                continue
            return identity_document
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
        allow_insecure_http: bool = False,
        allow_insecure_tls: bool = False,
        ca_file: str | None = None,
        mtls_enabled: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
        key_provider_info: dict[str, Any] | None = None,
    ) -> None:
        self._logger = logging.getLogger("acp.relay.router")
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
        self.policy = RelayHttpSecurityPolicy(
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=cert_file,
            key_file=key_file,
        )
        if key_provider_info is not None:
            self.resolver.config.key_provider_info = dict(key_provider_info)
        self._warned_messages: set[str] = set()
        try:
            warning_messages = validate_http_security_policy(
                self.policy,
                context="Relay router configuration",
            )
        except HttpSecurityError as exc:
            raise RuntimeError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)

    def _resolve_sender_identity_document(self, message: dict[str, Any]) -> dict[str, Any]:
        sender_identity_document = message.get("sender_identity_document")
        if isinstance(sender_identity_document, dict):
            return sender_identity_document

        envelope = message.get("envelope", {})
        sender = envelope.get("sender") if isinstance(envelope, dict) else None
        if not isinstance(sender, str) or not sender.strip():
            raise IdentityVerificationError("Message sender is missing")
        try:
            return self.resolver.resolve(sender)
        except LookupError as exc:
            raise IdentityVerificationError(
                f"Unable to resolve sender identity document for {sender}",
            ) from exc

    @staticmethod
    def _invalid_signature_outcomes(
        *,
        recipients: list[str],
        detail: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "recipient": recipient,
                "state": "FAILED",
                "reason_code": "INVALID_SIGNATURE",
                "detail": detail,
            }
            for recipient in recipients
        ]

    def _emit_warning(self, message: str) -> None:
        if message in self._warned_messages:
            return
        self._warned_messages.add(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _verify_for_url(self, url: str, *, context: str) -> tuple[bool | str, tuple[str, str] | None]:
        try:
            warning_messages = enforce_http_security(url, policy=self.policy, context=context)
        except HttpSecurityError as exc:
            raise RuntimeError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        try:
            cert = requests_cert_value(url, policy=self.policy)
        except HttpSecurityError as exc:
            raise RuntimeError(str(exc)) from exc
        return requests_verify_value(url, policy=self.policy), cert

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

    def routing_snapshot(self) -> dict[str, Any]:
        return {
            "discovery": {
                "well_known_path": "/.well-known/acp",
                "identity_resolution": "well_known_identity_document_reference",
            },
            "timeout_seconds": self.timeout_seconds,
            "store_and_forward": self.store_and_forward,
            "max_retry_attempts": self.max_retry_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "http_security": {
                "allow_insecure_http": self.policy.allow_insecure_http,
                "allow_insecure_tls": self.policy.allow_insecure_tls,
                "ca_file": self.policy.ca_file,
                "mtls_enabled": self.policy.mtls_enabled,
                "cert_file": self.policy.cert_file,
                "key_file": self.policy.key_file,
                "profile": security_profile(self.policy),
                "key_provider": dict(self.resolver.config.key_provider_info or {}),
            },
            "amqp": {
                "enabled": bool(self.amqp_publisher.default_broker_url),
                "default_exchange": self.amqp_publisher.default_exchange,
                "exchange_type": self.amqp_publisher.exchange_type,
            },
        }

    def _deliver_to_endpoint(
        self,
        *,
        recipient: str,
        endpoint: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {"recipient": recipient, "state": "FAILED", "retriable": False}
        self._logger.info("http_delivery_start recipient=%s endpoint=%s", recipient, endpoint)
        try:
            verify, cert = self._verify_for_url(endpoint, context="Relay delivery endpoint")
        except RuntimeError as exc:
            outcome["detail"] = str(exc)
            outcome["reason_code"] = "POLICY_REJECTED"
            self._logger.warning(
                "http_delivery_rejected recipient=%s endpoint=%s detail=%s",
                recipient,
                endpoint,
                outcome["detail"],
            )
            return outcome
        try:
            response = requests.post(
                endpoint,
                json=message,
                timeout=self.timeout_seconds,
                verify=verify,
                cert=cert,
            )
        except requests.RequestException as exc:
            outcome["detail"] = f"Delivery transport error: {exc}"
            outcome["reason_code"] = "POLICY_REJECTED"
            outcome["retriable"] = True
            self._logger.warning(
                "http_delivery_transport_error recipient=%s endpoint=%s detail=%s",
                recipient,
                endpoint,
                outcome["detail"],
            )
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
        self._logger.info(
            "http_delivery_complete recipient=%s endpoint=%s status_code=%s state=%s",
            recipient,
            endpoint,
            response.status_code,
            outcome["state"],
        )
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
        self._logger.info(
            "queued_retry message_id=%s operation_id=%s recipient=%s endpoint=%s",
            message_id,
            operation_id,
            recipient,
            endpoint,
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
            self._logger.warning(
                "amqp_delivery_failed recipient=%s detail=%s",
                recipient,
                str(exc),
            )
            return {
                "recipient": recipient,
                "state": "FAILED",
                "reason_code": "POLICY_REJECTED",
                "detail": str(exc),
            }
        self._logger.info("amqp_delivery_succeeded recipient=%s", recipient)
        return {
            "recipient": recipient,
            "state": "DELIVERED",
            "transport": "amqp",
        }

    def route_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        envelope = message.get("envelope", {})
        recipients = envelope.get("recipients", [])
        if not isinstance(recipients, list):
            return []
        normalized_recipients = [
            item for item in recipients if isinstance(item, str) and item.strip()
        ]
        outcomes: list[dict[str, Any]] = []
        message_id = envelope.get("message_id") if isinstance(envelope, dict) else None

        self._logger.info(
            "route_message_start message_id=%s recipients=%s",
            message_id,
            len(normalized_recipients),
        )

        try:
            sender_identity_document = self._resolve_sender_identity_document(message)
            verify_message_signature(
                message,
                sender_identity_document=sender_identity_document,
            )
        except IdentityVerificationError as exc:
            detail = str(exc)
            self._logger.warning(
                "route_message_rejected_invalid_signature message_id=%s detail=%s",
                message_id,
                detail,
            )
            return self._invalid_signature_outcomes(
                recipients=normalized_recipients,
                detail=detail,
            )

        for recipient in normalized_recipients:
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

        self._logger.info(
            "route_message_complete message_id=%s outcomes=%s",
            message_id,
            len(outcomes),
        )
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
        if processed:
            self._logger.info("processed_pending_deliveries count=%s", len(processed))
        return processed
