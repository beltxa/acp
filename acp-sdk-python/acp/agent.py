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
    ACP_VERSION,
    ACPMessage,
    CompensateInstruction,
    DEFAULT_CRYPTO_SUITE,
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


@dataclass
class ResolvedRecipient:
    recipient: str
    public_key: str
    identity_document: dict[str, Any]
    delivery_channel: str
    endpoint: str | None = None


def _reason_for_capability_mismatch(reason: str | None) -> FailReason:
    reason_lower = (reason or "").lower()
    if "protocol" in reason_lower:
        return FailReason.UNSUPPORTED_VERSION
    if "crypto" in reason_lower:
        return FailReason.UNSUPPORTED_CRYPTO_SUITE
    if "profile" in reason_lower:
        return FailReason.UNSUPPORTED_PROFILE
    return FailReason.POLICY_REJECTED


def _delivery_state_from_response(
    *,
    status_code: int,
    response_class: MessageClass | None,
    reason_code: str | None,
) -> DeliveryState:
    if 200 <= status_code < 300:
        if response_class is MessageClass.FAIL:
            if reason_code == FailReason.EXPIRED_MESSAGE.value:
                return DeliveryState.EXPIRED
            if reason_code == FailReason.POLICY_REJECTED.value:
                return DeliveryState.DECLINED
            return DeliveryState.FAILED
        if response_class in {MessageClass.ACK, MessageClass.CAPABILITIES}:
            return DeliveryState.ACKNOWLEDGED
        return DeliveryState.DELIVERED
    if status_code == 410:
        return DeliveryState.EXPIRED
    if status_code in {401, 403, 409, 422}:
        return DeliveryState.DECLINED
    return DeliveryState.FAILED


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
    def create(
        cls,
        agent_id: str,
        *,
        storage_dir: str | Path = ".acp-data",
        endpoint: str | None = None,
        relay_url: str = "http://localhost:8080",
        relay_hints: list[str] | None = None,
        enterprise_directory_hints: list[str] | None = None,
        discovery_scheme: str = "https",
        trust_profile: str = "self_asserted",
        capabilities: AgentCapabilities | None = None,
    ) -> "Agent":
        return cls.load_or_create(
            agent_id,
            storage_dir=storage_dir,
            endpoint=endpoint,
            relay_url=relay_url,
            relay_hints=relay_hints,
            enterprise_directory_hints=enterprise_directory_hints,
            discovery_scheme=discovery_scheme,
            trust_profile=trust_profile,
            capabilities=capabilities,
        )

    @classmethod
    def load_or_create(
        cls,
        agent_id: str,
        *,
        storage_dir: str | Path = ".acp-data",
        endpoint: str | None = None,
        relay_url: str = "http://localhost:8080",
        relay_hints: list[str] | None = None,
        enterprise_directory_hints: list[str] | None = None,
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
            enterprise_directory_hints=enterprise_directory_hints,
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

    def _shared_transports(self, remote_capabilities: AgentCapabilities) -> list[str]:
        remote_transports = {item.lower() for item in remote_capabilities.transports}
        shared: list[str] = []
        for transport in self.capabilities.transports:
            normalized = transport.lower()
            if normalized in remote_transports:
                shared.append(normalized)
        return shared

    def _choose_delivery_channel(
        self,
        *,
        remote_capabilities: AgentCapabilities,
        identity_doc: dict[str, Any],
        delivery_mode: str,
    ) -> tuple[str | None, str | None]:
        shared_transports = self._shared_transports(remote_capabilities)
        direct_endpoint = identity_doc.get("service", {}).get("direct_endpoint")
        has_direct_endpoint = isinstance(direct_endpoint, str) and bool(direct_endpoint.strip())

        def _direct_available() -> bool:
            if not has_direct_endpoint:
                return False
            return any(transport in {"https", "http", "direct"} for transport in shared_transports)

        if delivery_mode == "direct":
            if _direct_available():
                return "direct", str(direct_endpoint)
            return None, "No compatible direct transport and endpoint available"

        if delivery_mode == "relay":
            if "relay" in shared_transports:
                return "relay", None
            return None, "No compatible relay transport available"

        for transport in shared_transports:
            if transport in {"https", "http", "direct"} and _direct_available():
                return "direct", str(direct_endpoint)
            if transport == "relay":
                return "relay", None

        if has_direct_endpoint:
            return None, "No compatible transport implementation available for this recipient"
        return None, "Recipient identity document is missing direct_endpoint and no relay fallback is compatible"

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
        delivery_mode: str,
    ) -> tuple[list[ResolvedRecipient], list[DeliveryOutcome]]:
        resolved: list[ResolvedRecipient] = []
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

            delivery_channel, endpoint = self._choose_delivery_channel(
                remote_capabilities=remote_capabilities,
                identity_doc=identity_doc,
                delivery_mode=delivery_mode,
            )
            if delivery_channel is None:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=endpoint,
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

            resolved.append(
                ResolvedRecipient(
                    recipient=recipient,
                    public_key=recipient_public_key,
                    identity_document=identity_doc,
                    delivery_channel=delivery_channel,
                    endpoint=endpoint,
                ),
            )

        return resolved, outcomes

    def _outcome_from_http_response(
        self,
        *,
        recipient: str,
        status_code: int,
        body: dict[str, Any] | None,
    ) -> DeliveryOutcome:
        response_message = body.get("response_message") if isinstance(body, dict) else None
        response_class_raw = (
            response_message.get("envelope", {}).get("message_class")
            if isinstance(response_message, dict)
            else None
        )
        response_class: MessageClass | None = None
        if isinstance(response_class_raw, str):
            try:
                response_class = MessageClass(response_class_raw)
            except ValueError:
                response_class = None

        reason_code = body.get("reason_code") if isinstance(body, dict) else None
        detail = body.get("detail") if isinstance(body, dict) else None
        if not isinstance(reason_code, str):
            reason_code = None
        if not isinstance(detail, str):
            detail = None
        if detail is None and status_code >= 400:
            detail = f"Recipient HTTP {status_code}"

        return DeliveryOutcome(
            recipient=recipient,
            state=_delivery_state_from_response(
                status_code=status_code,
                response_class=response_class,
                reason_code=reason_code,
            ),
            status_code=status_code,
            response_class=response_class,
            reason_code=reason_code,
            detail=detail,
            response_message=response_message if isinstance(response_message, dict) else None,
        )

    def _deliver_direct(
        self,
        *,
        message: ACPMessage,
        targets: list[ResolvedRecipient],
    ) -> list[DeliveryOutcome]:
        outcomes: list[DeliveryOutcome] = []
        for target in targets:
            if target.endpoint is None:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail="Missing direct endpoint for direct delivery",
                    ),
                )
                continue
            try:
                response = self.relay_client.transport.post_json(target.endpoint, message.to_dict())
            except TransportError as exc:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=f"Direct transport failure: {exc}",
                    ),
                )
                continue
            try:
                body = response.json()
            except ValueError:
                body = None
            outcomes.append(
                self._outcome_from_http_response(
                    recipient=target.recipient,
                    status_code=response.status_code,
                    body=body if isinstance(body, dict) else None,
                ),
            )
        return outcomes

    def _deliver_via_relay(
        self,
        *,
        message: ACPMessage,
        targets: list[ResolvedRecipient],
    ) -> list[DeliveryOutcome]:
        expected_recipients = {target.recipient for target in targets}
        outcomes: list[DeliveryOutcome] = []
        try:
            relay_response = self.relay_client.send_message(message)
        except TransportError as exc:
            for recipient in expected_recipients:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=f"Relay transport failure: {exc}",
                    ),
                )
            return outcomes

        delivered: set[str] = set()
        for raw_outcome in relay_response.get("outcomes", []):
            try:
                outcome = DeliveryOutcome.from_dict(raw_outcome)
            except Exception:  # noqa: BLE001
                continue
            delivered.add(outcome.recipient)
            outcomes.append(outcome)

        for recipient in expected_recipients - delivered:
            outcomes.append(
                DeliveryOutcome(
                    recipient=recipient,
                    state=DeliveryState.FAILED,
                    reason_code=FailReason.POLICY_REJECTED.value,
                    detail="Relay did not return an outcome for recipient",
                ),
            )
        return outcomes

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
        delivery_mode: str = "auto",
    ) -> SendResult:
        if not recipients:
            raise ValueError("send() requires at least one recipient")
        if delivery_mode not in {"auto", "direct", "relay"}:
            raise ValueError("delivery_mode must be one of: auto, direct, relay")

        operation_id = str(uuid.uuid4())
        context_id = context or operation_id

        resolved_recipients, preflight_outcomes = self._resolve_recipients(
            recipients,
            delivery_mode=delivery_mode,
        )
        if not resolved_recipients:
            result = SendResult(
                operation_id=operation_id,
                message_id=str(uuid.uuid4()),
                outcomes=preflight_outcomes,
            )
            self._sync_delivery_states(operation_id, preflight_outcomes)
            return result

        outcomes = [*preflight_outcomes]
        outbound_message_ids: list[str] = []

        direct_targets = [
            target for target in resolved_recipients if target.delivery_channel == "direct"
        ]
        relay_targets = [
            target for target in resolved_recipients if target.delivery_channel == "relay"
        ]

        if direct_targets:
            direct_message = self._build_message(
                recipients=[target.recipient for target in direct_targets],
                payload=payload,
                recipient_public_keys={
                    target.recipient: target.public_key for target in direct_targets
                },
                message_class=message_class,
                context_id=context_id,
                operation_id=operation_id,
                expires_in_seconds=expires_in_seconds,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
            )
            outbound_message_ids.append(direct_message.envelope.message_id)
            outcomes.extend(
                self._deliver_direct(
                    message=direct_message,
                    targets=direct_targets,
                ),
            )

        if relay_targets:
            relay_message = self._build_message(
                recipients=[target.recipient for target in relay_targets],
                payload=payload,
                recipient_public_keys={
                    target.recipient: target.public_key for target in relay_targets
                },
                message_class=message_class,
                context_id=context_id,
                operation_id=operation_id,
                expires_in_seconds=expires_in_seconds,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
            )
            outbound_message_ids.append(relay_message.envelope.message_id)
            outcomes.extend(
                self._deliver_via_relay(
                    message=relay_message,
                    targets=relay_targets,
                ),
            )

        result = SendResult(
            operation_id=operation_id,
            message_id=outbound_message_ids[0],
            outcomes=outcomes,
            message_ids=outbound_message_ids,
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
        delivery_mode: str = "auto",
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
            delivery_mode=delivery_mode,
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
        if message.envelope.acp_version != ACP_VERSION:
            raise ProcessingError(
                reason_code=FailReason.UNSUPPORTED_VERSION,
                detail=f"Unsupported ACP version: {message.envelope.acp_version}",
            )
        if message.envelope.crypto_suite != DEFAULT_CRYPTO_SUITE:
            raise ProcessingError(
                reason_code=FailReason.UNSUPPORTED_CRYPTO_SUITE,
                detail=f"Unsupported crypto suite: {message.envelope.crypto_suite}",
            )
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
            if request_message.envelope.acp_version != ACP_VERSION:
                raise ProcessingError(
                    reason_code=FailReason.UNSUPPORTED_VERSION,
                    detail=f"Unsupported ACP version: {request_message.envelope.acp_version}",
                )
            if request_message.envelope.crypto_suite != DEFAULT_CRYPTO_SUITE:
                raise ProcessingError(
                    reason_code=FailReason.UNSUPPORTED_CRYPTO_SUITE,
                    detail=f"Unsupported crypto suite: {request_message.envelope.crypto_suite}",
                )
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
