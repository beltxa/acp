from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

from .capabilities import AgentCapabilities, choose_compatible
from .crypto import (
    CryptoError,
    decrypt_for_recipient,
    encrypt_for_recipients,
    sign_protected_payload,
    verify_protected_payload_signature,
)
from .discovery import DiscoveryClient, DiscoveryError
from .identity import AgentIdentity, parse_agent_id, read_identity, verify_identity_document, write_identity
from .messages import (
    ACPMessage,
    CompensateInstruction,
    DeliveryOutcome,
    DeliveryState,
    Envelope,
    FailReason,
    MessageClass,
    SendResult,
    build_ack_payload,
    build_fail_payload,
)
from .relay_client import RelayClient
from .transport import TransportError


IncomingHandler = Callable[[dict[str, Any], Envelope], Optional[dict[str, Any]]]


@dataclass
class ProcessingError(RuntimeError):
    reason_code: FailReason
    detail: str


def _reason_for_capability_mismatch(reason: str | None) -> FailReason:
    reason_lower = (reason or "").lower()
    if "protocol" in reason_lower:
        return FailReason.UNSUPPORTED_VERSION
    if "crypto" in reason_lower:
        return FailReason.UNSUPPORTED_CRYPTO_SUITE
    if "profile" in reason_lower:
        return FailReason.UNSUPPORTED_PROFILE
    return FailReason.POLICY_REJECTED


class Agent:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        identity_document: dict[str, Any],
        discovery: DiscoveryClient,
        relay_client: RelayClient,
        capabilities: AgentCapabilities,
        storage_dir: Path,
        trust_profile: str,
    ) -> None:
        self.identity = identity
        self.identity_document = identity_document
        self.discovery = discovery
        self.relay_client = relay_client
        self.capabilities = capabilities
        self.storage_dir = storage_dir
        self.trust_profile = trust_profile
        self.delivery_states: dict[str, dict[str, str]] = {}

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @classmethod
    def load_or_create(
        cls,
        agent_id: str,
        *,
        storage_dir: str | Path = ".acp-data",
        endpoint: str | None = None,
        relay_url: str = "http://localhost:8080",
        relay_hints: list[str] | None = None,
        discovery_scheme: str = "https",
        trust_profile: str = "self_asserted",
        capabilities: AgentCapabilities | None = None,
    ) -> "Agent":
        parse_agent_id(agent_id)
        storage = Path(storage_dir)
        storage.mkdir(parents=True, exist_ok=True)

        existing = read_identity(storage, agent_id)
        if existing is None:
            identity = AgentIdentity.create(agent_id)
            capabilities_obj = capabilities or AgentCapabilities(agent_id=agent_id)
            identity_document = identity.build_identity_document(
                direct_endpoint=endpoint,
                relay_hints=relay_hints,
                trust_profile=trust_profile,
                capabilities=capabilities_obj.to_dict(),
            )
            write_identity(storage, identity, identity_document)
        else:
            identity, identity_document = existing
            if not verify_identity_document(identity_document):
                capabilities_obj = capabilities or AgentCapabilities(agent_id=agent_id)
                identity_document = identity.build_identity_document(
                    direct_endpoint=endpoint,
                    relay_hints=relay_hints,
                    trust_profile=trust_profile,
                    capabilities=capabilities_obj.to_dict(),
                )
                write_identity(storage, identity, identity_document)
            else:
                capabilities_obj = capabilities or AgentCapabilities.from_dict(
                    identity_document.get("capabilities"),
                    fallback_agent_id=agent_id,
                )
                if endpoint is not None or relay_hints is not None or capabilities is not None:
                    identity_document = identity.build_identity_document(
                        direct_endpoint=endpoint
                        if endpoint is not None
                        else identity_document.get("service", {}).get("direct_endpoint"),
                        relay_hints=relay_hints
                        if relay_hints is not None
                        else identity_document.get("service", {}).get("relay_hints", []),
                        trust_profile=trust_profile,
                        capabilities=capabilities_obj.to_dict(),
                    )
                    write_identity(storage, identity, identity_document)

        effective_hints = relay_hints if relay_hints is not None else identity_document.get(
            "service",
            {},
        ).get(
            "relay_hints",
            [],
        )
        if relay_url and relay_url not in effective_hints:
            effective_hints = [*effective_hints, relay_url]

        discovery = DiscoveryClient(
            cache_path=storage / "discovery_cache.json",
            default_scheme=discovery_scheme,
            relay_hints=effective_hints,
        )
        discovery.seed(identity_document)

        return cls(
            identity=identity,
            identity_document=identity_document,
            discovery=discovery,
            relay_client=RelayClient(relay_url),
            capabilities=capabilities_obj,
            storage_dir=storage,
            trust_profile=trust_profile,
        )

    def _build_message(
        self,
        *,
        recipients: list[str],
        payload: dict[str, Any],
        recipient_public_keys: dict[str, str],
        message_class: MessageClass,
        context_id: str,
        operation_id: str,
        expires_in_seconds: int,
        correlation_id: str | None,
        in_reply_to: str | None,
    ) -> ACPMessage:
        envelope = Envelope.build(
            sender=self.agent_id,
            recipients=recipients,
            message_class=message_class,
            context_id=context_id,
            expires_in_seconds=expires_in_seconds,
            operation_id=operation_id,
            correlation_id=correlation_id,
            in_reply_to=in_reply_to,
        )
        protected = encrypt_for_recipients(payload, envelope, recipient_public_keys)
        protected = sign_protected_payload(
            envelope,
            protected,
            self.identity.signing_private_key,
            self.identity.signing_kid,
        )
        return ACPMessage(
            envelope=envelope,
            protected=protected,
            sender_identity_document=self.identity_document,
        )

    def _resolve_sender_identity_document(
        self,
        *,
        raw_message: dict[str, Any],
        sender_id: str,
    ) -> dict[str, Any]:
        embedded_identity_document = raw_message.get("sender_identity_document")
        if (
            isinstance(embedded_identity_document, dict)
            and embedded_identity_document.get("agent_id") == sender_id
            and verify_identity_document(embedded_identity_document)
        ):
            return embedded_identity_document
        return self.discovery.resolve(sender_id)

    def _resolve_recipients(
        self,
        recipients: list[str],
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[DeliveryOutcome]]:
        public_keys: dict[str, str] = {}
        identity_docs: dict[str, dict[str, Any]] = {}
        outcomes: list[DeliveryOutcome] = []

        for recipient in recipients:
            try:
                identity_doc = self.discovery.resolve(recipient)
            except DiscoveryError as exc:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=str(exc),
                    ),
                )
                continue

            remote_capabilities = AgentCapabilities.from_dict(
                identity_doc.get("capabilities"),
                fallback_agent_id=recipient,
            )
            capability_match = choose_compatible(self.capabilities, remote_capabilities)
            if not capability_match.is_compatible:
                fail_reason = _reason_for_capability_mismatch(capability_match.reason)
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=fail_reason.value,
                        detail=capability_match.reason,
                    ),
                )
                continue

            recipient_public_key = (
                identity_doc.get("keys", {}).get("encryption", {}).get("public_key")
            )
            if not isinstance(recipient_public_key, str):
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail="Recipient identity document missing encryption public key",
                    ),
                )
                continue

            identity_docs[recipient] = identity_doc
            public_keys[recipient] = recipient_public_key

        return public_keys, identity_docs, outcomes

    def _sync_delivery_states(self, operation_id: str, outcomes: list[DeliveryOutcome]) -> None:
        self.delivery_states[operation_id] = {
            outcome.recipient: outcome.state.value for outcome in outcomes
        }

    def send(
        self,
        *,
        recipients: list[str],
        payload: dict[str, Any],
        context: str | None = None,
        message_class: MessageClass = MessageClass.SEND,
        expires_in_seconds: int = 300,
        correlation_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> SendResult:
        if not recipients:
            raise ValueError("send() requires at least one recipient")

        operation_id = str(uuid.uuid4())
        context_id = context or operation_id

        public_keys, _identity_docs, preflight_outcomes = self._resolve_recipients(recipients)
        deliverable_recipients = list(public_keys.keys())
        if not deliverable_recipients:
            result = SendResult(
                operation_id=operation_id,
                message_id=str(uuid.uuid4()),
                outcomes=preflight_outcomes,
            )
            self._sync_delivery_states(operation_id, preflight_outcomes)
            return result

        message = self._build_message(
            recipients=deliverable_recipients,
            payload=payload,
            recipient_public_keys=public_keys,
            message_class=message_class,
            context_id=context_id,
            operation_id=operation_id,
            expires_in_seconds=expires_in_seconds,
            correlation_id=correlation_id,
            in_reply_to=in_reply_to,
        )

        outcomes = [*preflight_outcomes]
        try:
            relay_response = self.relay_client.send_message(message)
        except TransportError as exc:
            for recipient in deliverable_recipients:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=f"Relay transport failure: {exc}",
                    ),
                )
            result = SendResult(
                operation_id=operation_id,
                message_id=message.envelope.message_id,
                outcomes=outcomes,
            )
            self._sync_delivery_states(operation_id, outcomes)
            return result

        delivered = set()
        for raw_outcome in relay_response.get("outcomes", []):
            outcome = DeliveryOutcome.from_dict(raw_outcome)
            delivered.add(outcome.recipient)
            outcomes.append(outcome)

        for recipient in deliverable_recipients:
            if recipient not in delivered:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail="Relay did not return an outcome for recipient",
                    ),
                )

        result = SendResult(
            operation_id=operation_id,
            message_id=message.envelope.message_id,
            outcomes=outcomes,
        )
        self._sync_delivery_states(operation_id, outcomes)
        return result

    def send_compensate(
        self,
        *,
        recipients: list[str],
        original_operation_id: str,
        reason: str,
        actions: list[dict[str, Any]] | None = None,
        context: str | None = None,
    ) -> SendResult:
        instruction = CompensateInstruction(
            operation_id=original_operation_id,
            reason=reason,
            actions=actions or [],
        )
        return self.send(
            recipients=recipients,
            payload={"compensation": instruction.to_dict()},
            context=context or f"compensate:{original_operation_id}",
            message_class=MessageClass.COMPENSATE,
            correlation_id=original_operation_id,
        )

    def _create_response_message(
        self,
        *,
        sender_identity_document: dict[str, Any],
        request_envelope: Envelope,
        response_message_class: MessageClass,
        response_payload: dict[str, Any],
    ) -> ACPMessage:
        sender_id = request_envelope.sender
        sender_encryption_public_key = (
            sender_identity_document.get("keys", {}).get("encryption", {}).get("public_key")
        )
        if not isinstance(sender_encryption_public_key, str):
            raise ProcessingError(
                reason_code=FailReason.POLICY_REJECTED,
                detail="Sender identity document missing encryption key",
            )

        return self._build_message(
            recipients=[sender_id],
            payload=response_payload,
            recipient_public_keys={sender_id: sender_encryption_public_key},
            message_class=response_message_class,
            context_id=request_envelope.context_id,
            operation_id=request_envelope.operation_id,
            expires_in_seconds=300,
            correlation_id=request_envelope.correlation_id or request_envelope.operation_id,
            in_reply_to=request_envelope.message_id,
        )

    def decrypt_message_for_self(self, raw_message: dict[str, Any]) -> tuple[ACPMessage, dict[str, Any]]:
        message = ACPMessage.from_dict(raw_message)
        if self.agent_id not in message.envelope.recipients:
            raise ProcessingError(
                reason_code=FailReason.POLICY_REJECTED,
                detail="Message is not addressed to this agent",
            )
        if message.envelope.is_expired():
            raise ProcessingError(
                reason_code=FailReason.EXPIRED_MESSAGE,
                detail=f"Message {message.envelope.message_id} is expired",
            )

        sender_doc = self._resolve_sender_identity_document(
            raw_message=raw_message,
            sender_id=message.envelope.sender,
        )
        sender_signing_key = sender_doc.get("keys", {}).get("signing", {}).get("public_key")
        if not isinstance(sender_signing_key, str):
            raise ProcessingError(
                reason_code=FailReason.INVALID_SIGNATURE,
                detail="Sender signing public key is missing from identity document",
            )
        if not verify_protected_payload_signature(
            message.envelope,
            message.protected,
            sender_signing_key,
        ):
            raise ProcessingError(
                reason_code=FailReason.INVALID_SIGNATURE,
                detail="Message signature verification failed",
            )

        try:
            payload = decrypt_for_recipient(
                message.envelope,
                message.protected,
                self.agent_id,
                self.identity.encryption_private_key,
            )
        except CryptoError as exc:
            raise ProcessingError(
                reason_code=FailReason.POLICY_REJECTED,
                detail=str(exc),
            ) from exc
        return message, payload

    def handle_incoming(
        self,
        raw_message: dict[str, Any],
        *,
        handler: IncomingHandler | None = None,
    ) -> dict[str, Any]:
        response_state = DeliveryState.FAILED
        decrypted_payload: dict[str, Any] | None = None
        reason_code: str | None = None
        detail: str | None = None
        response_message: ACPMessage | None = None

        try:
            request_message = ACPMessage.from_dict(raw_message)
        except Exception as exc:  # noqa: BLE001
            return {
                "state": DeliveryState.FAILED.value,
                "reason_code": FailReason.POLICY_REJECTED.value,
                "detail": f"Invalid ACP message structure: {exc}",
                "response_message": None,
            }

        sender_identity_document: dict[str, Any] | None = None
        try:
            if request_message.envelope.is_expired():
                raise ProcessingError(
                    reason_code=FailReason.EXPIRED_MESSAGE,
                    detail="Message is expired",
                )
            if self.agent_id not in request_message.envelope.recipients:
                raise ProcessingError(
                    reason_code=FailReason.POLICY_REJECTED,
                    detail=f"Recipient {self.agent_id} not in message recipients",
                )

            sender_identity_document = self._resolve_sender_identity_document(
                raw_message=raw_message,
                sender_id=request_message.envelope.sender,
            )
            sender_signing_key = (
                sender_identity_document.get("keys", {}).get("signing", {}).get("public_key")
            )
            if not isinstance(sender_signing_key, str):
                raise ProcessingError(
                    reason_code=FailReason.INVALID_SIGNATURE,
                    detail="Sender signing key missing from identity document",
                )

            if not verify_protected_payload_signature(
                request_message.envelope,
                request_message.protected,
                sender_signing_key,
            ):
                raise ProcessingError(
                    reason_code=FailReason.INVALID_SIGNATURE,
                    detail="Signature verification failed",
                )

            decrypted_payload = decrypt_for_recipient(
                request_message.envelope,
                request_message.protected,
                self.agent_id,
                self.identity.encryption_private_key,
            )

            if request_message.envelope.message_class is MessageClass.CAPABILITIES:
                response_state = DeliveryState.ACKNOWLEDGED
                response_payload = self.capabilities.to_dict()
                response_message = self._create_response_message(
                    sender_identity_document=sender_identity_document,
                    request_envelope=request_message.envelope,
                    response_message_class=MessageClass.CAPABILITIES,
                    response_payload=response_payload,
                )
            else:
                handler_payload: dict[str, Any] | None = None
                if handler is not None:
                    handler_payload = handler(decrypted_payload, request_message.envelope)
                response_state = DeliveryState.ACKNOWLEDGED
                ack_payload = build_ack_payload(request_message.envelope.message_id)
                if handler_payload:
                    ack_payload["handler"] = handler_payload
                response_message = self._create_response_message(
                    sender_identity_document=sender_identity_document,
                    request_envelope=request_message.envelope,
                    response_message_class=MessageClass.ACK,
                    response_payload=ack_payload,
                )
        except ProcessingError as exc:
            reason_code = exc.reason_code.value
            detail = exc.detail
        except DiscoveryError as exc:
            reason_code = FailReason.POLICY_REJECTED.value
            detail = f"Discovery failed for sender identity: {exc}"
        except CryptoError as exc:
            reason_code = FailReason.POLICY_REJECTED.value
            detail = str(exc)
        except Exception as exc:  # noqa: BLE001
            reason_code = FailReason.POLICY_REJECTED.value
            detail = str(exc)

        if response_state is DeliveryState.FAILED:
            if reason_code is None:
                reason_code = FailReason.POLICY_REJECTED.value
            if detail is None:
                detail = "Message processing failed"
            if sender_identity_document is not None:
                try:
                    fail_payload = build_fail_payload(reason_code=reason_code, detail=detail)
                    response_message = self._create_response_message(
                        sender_identity_document=sender_identity_document,
                        request_envelope=request_message.envelope,
                        response_message_class=MessageClass.FAIL,
                        response_payload=fail_payload,
                    )
                except Exception:  # noqa: BLE001
                    response_message = None

        return {
            "state": response_state.value,
            "reason_code": reason_code,
            "detail": detail,
            "decrypted_payload": decrypted_payload,
            "response_message": response_message.to_dict() if response_message else None,
        }

    def request_capabilities(self, recipient: str) -> tuple[SendResult, dict[str, Any] | None]:
        result = self.send(
            recipients=[recipient],
            payload={"request": "capabilities"},
            message_class=MessageClass.CAPABILITIES,
            context=f"capabilities:{uuid.uuid4()}",
        )

        response_payload: dict[str, Any] | None = None
        for outcome in result.outcomes:
            if outcome.response_message is None:
                continue
            try:
                response_message, payload = self.decrypt_message_for_self(outcome.response_message)
            except Exception:  # noqa: BLE001
                continue
            if response_message.envelope.message_class is MessageClass.CAPABILITIES:
                response_payload = payload
                break
        return result, response_payload
