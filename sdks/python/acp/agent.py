# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
import uuid
import warnings
from urllib.parse import urlsplit

from .amqp_transport import (
    AMQPTransport,
    AMQPTransportError,
    DEFAULT_AMQP_EXCHANGE,
    build_amqp_service_hint,
)
from .mqtt_transport import (
    DEFAULT_MQTT_QOS,
    DEFAULT_MQTT_TOPIC_PREFIX,
    MQTTTransport,
    MQTTTransportError,
    build_mqtt_service_hint,
)
from .capabilities import AgentCapabilities, choose_compatible
from .crypto import (
    CryptoError,
    decrypt_for_recipient,
    encrypt_for_recipients,
    sign_protected_payload,
    verify_protected_payload_signature,
)
from .discovery import DiscoveryClient, DiscoveryError
from .http_security import (
    HttpSecurityError,
    HttpSecurityPolicy,
    enforce_http_security,
    validate_http_security_policy,
)
from .identity import AgentIdentity, parse_agent_id, read_identity, verify_identity_document, write_identity
from .key_provider import IdentityKeyMaterial, KeyProvider, KeyProviderError, LocalKeyProvider
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
from .well_known import build_well_known_document as build_well_known_metadata


IncomingHandler = Callable[[dict[str, Any], Envelope], Optional[dict[str, Any]]]


@dataclass
class ProcessingError(RuntimeError):
    reason_code: FailReason
    detail: str


def _identity_from_provider(agent_id: str, keys: IdentityKeyMaterial) -> AgentIdentity:
    missing: list[str] = []
    if not keys.signing_public_key:
        missing.append("signing_public_key")
    if not keys.encryption_public_key:
        missing.append("encryption_public_key")
    if not keys.signing_kid:
        missing.append("signing_kid")
    if not keys.encryption_kid:
        missing.append("encryption_kid")
    if missing:
        raise TransportError(
            "External key provider requires identity public metadata for first-time bootstrap: "
            + ", ".join(missing),
        )
    return AgentIdentity(
        agent_id=agent_id,
        signing_private_key=keys.signing_private_key,
        signing_public_key=str(keys.signing_public_key),
        encryption_private_key=keys.encryption_private_key,
        encryption_public_key=str(keys.encryption_public_key),
        signing_kid=str(keys.signing_kid),
        encryption_kid=str(keys.encryption_kid),
    )


def _apply_provider_keys(identity: AgentIdentity, keys: IdentityKeyMaterial) -> AgentIdentity:
    if keys.signing_public_key and keys.signing_public_key != identity.signing_public_key:
        raise TransportError("Key provider signing_public_key does not match local identity metadata")
    if keys.encryption_public_key and keys.encryption_public_key != identity.encryption_public_key:
        raise TransportError("Key provider encryption_public_key does not match local identity metadata")
    if keys.signing_kid and keys.signing_kid != identity.signing_kid:
        raise TransportError("Key provider signing_kid does not match local identity metadata")
    if keys.encryption_kid and keys.encryption_kid != identity.encryption_kid:
        raise TransportError("Key provider encryption_kid does not match local identity metadata")
    return AgentIdentity(
        agent_id=identity.agent_id,
        signing_private_key=keys.signing_private_key,
        signing_public_key=identity.signing_public_key,
        encryption_private_key=keys.encryption_private_key,
        encryption_public_key=identity.encryption_public_key,
        signing_kid=identity.signing_kid,
        encryption_kid=identity.encryption_kid,
    )


@dataclass
class ResolvedRecipient:
    recipient: str
    public_key: str
    identity_document: dict[str, Any]
    delivery_channel: str
    endpoint: str | None = None
    amqp_service: dict[str, Any] | None = None
    mqtt_service: dict[str, Any] | None = None


def _reason_for_capability_mismatch(reason: str | None) -> FailReason:
    reason_lower = (reason or "").lower()
    if "protocol" in reason_lower:
        return FailReason.UNSUPPORTED_VERSION
    if "crypto" in reason_lower:
        return FailReason.UNSUPPORTED_CRYPTO_SUITE
    if "profile" in reason_lower:
        return FailReason.UNSUPPORTED_PROFILE
    return FailReason.POLICY_REJECTED


def _validate_http_config(
    *,
    url: str,
    policy: HttpSecurityPolicy,
    context: str,
) -> None:
    try:
        warning_messages = enforce_http_security(url, policy=policy, context=context)
    except HttpSecurityError as exc:
        raise TransportError(str(exc)) from exc
    for warning_message in warning_messages:
        warnings.warn(warning_message, RuntimeWarning, stacklevel=3)


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


def _base_url_from_endpoint(endpoint: Any) -> str | None:
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None
    parsed = urlsplit(endpoint.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


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
        amqp_transport: AMQPTransport | None,
        mqtt_transport: MQTTTransport | None,
        key_provider_info: dict[str, Any] | None,
    ) -> None:
        self.identity = identity
        self.identity_document = identity_document
        self.discovery = discovery
        self.relay_client = relay_client
        self.capabilities = capabilities
        self.storage_dir = storage_dir
        self.trust_profile = trust_profile
        self.amqp_transport = amqp_transport
        self.mqtt_transport = mqtt_transport
        self.key_provider_info = dict(key_provider_info or {})
        self.delivery_states: dict[str, dict[str, str]] = {}
        self._processed_message_ids: set[str] = set()

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    def build_well_known_document(
        self,
        *,
        base_url: str | None = None,
        identity_document_url: str | None = None,
    ) -> dict[str, Any]:
        resolved_base_url = base_url or _base_url_from_endpoint(
            self.identity_document.get("service", {}).get("direct_endpoint"),
        )
        if not isinstance(resolved_base_url, str) or not resolved_base_url.strip():
            raise TransportError(
                "Unable to build /.well-known/acp metadata without base_url or direct_endpoint",
            )
        return build_well_known_metadata(
            identity_document=self.identity_document,
            base_url=resolved_base_url,
            identity_document_url=identity_document_url,
        )

    @classmethod
    def create(
        cls,
        agent_id: str,
        *,
        storage_dir: str | Path = ".acp-data",
        endpoint: str | None = None,
        relay_url: str = "https://localhost:8080",
        relay_hints: list[str] | None = None,
        enterprise_directory_hints: list[str] | None = None,
        discovery_scheme: str = "https",
        trust_profile: str = "self_asserted",
        capabilities: AgentCapabilities | None = None,
        amqp_broker_url: str | None = None,
        amqp_exchange: str = DEFAULT_AMQP_EXCHANGE,
        amqp_exchange_type: str = "direct",
        mqtt_broker_url: str | None = None,
        mqtt_qos: int = DEFAULT_MQTT_QOS,
        mqtt_topic_prefix: str = DEFAULT_MQTT_TOPIC_PREFIX,
        allow_insecure_http: bool = False,
        allow_insecure_tls: bool = False,
        ca_file: str | None = None,
        mtls_enabled: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
        key_provider: KeyProvider | None = None,
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
            amqp_broker_url=amqp_broker_url,
            amqp_exchange=amqp_exchange,
            amqp_exchange_type=amqp_exchange_type,
            mqtt_broker_url=mqtt_broker_url,
            mqtt_qos=mqtt_qos,
            mqtt_topic_prefix=mqtt_topic_prefix,
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=cert_file,
            key_file=key_file,
            key_provider=key_provider,
        )

    @classmethod
    def load_or_create(
        cls,
        agent_id: str,
        *,
        storage_dir: str | Path = ".acp-data",
        endpoint: str | None = None,
        relay_url: str = "https://localhost:8080",
        relay_hints: list[str] | None = None,
        enterprise_directory_hints: list[str] | None = None,
        discovery_scheme: str = "https",
        trust_profile: str = "self_asserted",
        capabilities: AgentCapabilities | None = None,
        amqp_broker_url: str | None = None,
        amqp_exchange: str = DEFAULT_AMQP_EXCHANGE,
        amqp_exchange_type: str = "direct",
        mqtt_broker_url: str | None = None,
        mqtt_qos: int = DEFAULT_MQTT_QOS,
        mqtt_topic_prefix: str = DEFAULT_MQTT_TOPIC_PREFIX,
        allow_insecure_http: bool = False,
        allow_insecure_tls: bool = False,
        ca_file: str | None = None,
        mtls_enabled: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
        key_provider: KeyProvider | None = None,
    ) -> "Agent":
        parse_agent_id(agent_id)
        storage = Path(storage_dir)
        storage.mkdir(parents=True, exist_ok=True)
        provider = key_provider or LocalKeyProvider(
            storage_dir=storage,
            cert_file=cert_file,
            key_file=key_file,
            ca_file=ca_file,
        )
        try:
            key_provider_info = provider.describe()
        except Exception:  # noqa: BLE001
            key_provider_info = {"provider": "unknown"}

        provider_tls_material = None
        provider_ca_bundle: str | None = None
        try:
            provider_tls_material = provider.load_tls_material(agent_id)
        except KeyProviderError as exc:
            if mtls_enabled:
                raise TransportError(f"Unable to load TLS material from key provider: {exc}") from exc
        try:
            provider_ca_bundle = provider.load_ca_bundle(agent_id)
        except KeyProviderError:
            provider_ca_bundle = None

        effective_ca_file = (
            ca_file
            or (
                provider_tls_material.ca_file
                if provider_tls_material is not None and provider_tls_material.ca_file
                else None
            )
            or provider_ca_bundle
        )
        effective_cert_file = (
            cert_file
            or (
                provider_tls_material.cert_file
                if provider_tls_material is not None and provider_tls_material.cert_file
                else None
            )
        )
        effective_key_file = (
            key_file
            or (
                provider_tls_material.key_file
                if provider_tls_material is not None and provider_tls_material.key_file
                else None
            )
        )

        http_policy = HttpSecurityPolicy(
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=effective_ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=effective_cert_file,
            key_file=effective_key_file,
        )
        try:
            warning_messages = validate_http_security_policy(
                http_policy,
                context="Agent configuration",
            )
        except HttpSecurityError as exc:
            raise TransportError(str(exc)) from exc
        for warning_message in warning_messages:
            warnings.warn(warning_message, RuntimeWarning, stacklevel=3)
        if endpoint:
            _validate_http_config(
                url=endpoint,
                policy=http_policy,
                context="Agent direct endpoint configuration",
            )
        if relay_url:
            _validate_http_config(
                url=relay_url,
                policy=http_policy,
                context="Agent relay URL configuration",
            )
        for relay_hint in relay_hints or []:
            _validate_http_config(
                url=str(relay_hint),
                policy=http_policy,
                context="Agent relay hint configuration",
            )
        for directory_hint in enterprise_directory_hints or []:
            _validate_http_config(
                url=str(directory_hint),
                policy=http_policy,
                context="Agent enterprise directory hint configuration",
            )

        local_amqp_service = (
            build_amqp_service_hint(
                agent_id=agent_id,
                broker_url=amqp_broker_url,
                exchange=amqp_exchange,
            )
            if amqp_broker_url
            else None
        )
        local_mqtt_service = (
            build_mqtt_service_hint(
                agent_id=agent_id,
                broker_url=mqtt_broker_url,
                qos=mqtt_qos,
                topic_prefix=mqtt_topic_prefix,
            )
            if mqtt_broker_url
            else None
        )
        http_security_profile = "mtls" if mtls_enabled else None

        provider_identity_keys: IdentityKeyMaterial | None = None
        provider_identity_error: KeyProviderError | None = None
        try:
            provider_identity_keys = provider.load_identity_keys(agent_id)
        except KeyProviderError as exc:
            provider_identity_error = exc

        existing = read_identity(storage, agent_id)
        if existing is None:
            if provider_identity_keys is not None:
                identity = _identity_from_provider(agent_id, provider_identity_keys)
            elif key_provider is not None and not isinstance(provider, LocalKeyProvider):
                raise TransportError(
                    f"Unable to load identity keys from key provider: {provider_identity_error}",
                )
            else:
                identity = AgentIdentity.create(agent_id)
            capabilities_obj = capabilities or AgentCapabilities(agent_id=agent_id)
            identity_document = identity.build_identity_document(
                direct_endpoint=endpoint,
                relay_hints=relay_hints,
                http_security_profile=http_security_profile,
                relay_security_profile=http_security_profile,
                amqp_service=local_amqp_service,
                mqtt_service=local_mqtt_service,
                trust_profile=trust_profile,
                capabilities=capabilities_obj.to_dict(),
            )
            write_identity(storage, identity, identity_document)
        else:
            identity, identity_document = existing
            if provider_identity_keys is not None:
                identity = _apply_provider_keys(identity, provider_identity_keys)
            elif key_provider is not None and not isinstance(provider, LocalKeyProvider):
                raise TransportError(
                    f"Unable to load identity keys from key provider: {provider_identity_error}",
                )
            if not verify_identity_document(identity_document):
                capabilities_obj = capabilities or AgentCapabilities(agent_id=agent_id)
                identity_document = identity.build_identity_document(
                    direct_endpoint=endpoint,
                    relay_hints=relay_hints,
                    http_security_profile=http_security_profile,
                    relay_security_profile=http_security_profile,
                    amqp_service=local_amqp_service,
                    mqtt_service=local_mqtt_service,
                    trust_profile=trust_profile,
                    capabilities=capabilities_obj.to_dict(),
                )
                write_identity(storage, identity, identity_document)
            else:
                capabilities_obj = capabilities or AgentCapabilities.from_dict(
                    identity_document.get("capabilities"),
                    fallback_agent_id=agent_id,
                )
                if (
                    endpoint is not None
                    or relay_hints is not None
                    or capabilities is not None
                    or local_amqp_service is not None
                    or local_mqtt_service is not None
                ):
                    identity_document = identity.build_identity_document(
                        direct_endpoint=endpoint
                        if endpoint is not None
                        else identity_document.get("service", {}).get("direct_endpoint"),
                        relay_hints=relay_hints
                        if relay_hints is not None
                        else identity_document.get("service", {}).get("relay_hints", []),
                        http_security_profile=http_security_profile,
                        relay_security_profile=http_security_profile,
                        amqp_service=local_amqp_service
                        if local_amqp_service is not None
                        else identity_document.get("service", {}).get("amqp"),
                        mqtt_service=local_mqtt_service
                        if local_mqtt_service is not None
                        else identity_document.get("service", {}).get("mqtt"),
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
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=effective_ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=effective_cert_file,
            key_file=effective_key_file,
        )
        discovery.seed(identity_document)

        amqp_transport: AMQPTransport | None = None
        if amqp_broker_url:
            amqp_transport = AMQPTransport(
                broker_url=amqp_broker_url,
                exchange=amqp_exchange,
                exchange_type=amqp_exchange_type,
            )

        mqtt_transport: MQTTTransport | None = None
        if mqtt_broker_url:
            mqtt_transport = MQTTTransport(
                broker_url=mqtt_broker_url,
                qos=mqtt_qos,
                topic_prefix=mqtt_topic_prefix,
            )

        return cls(
            identity=identity,
            identity_document=identity_document,
            discovery=discovery,
            relay_client=RelayClient(
                relay_url,
                allow_insecure_http=allow_insecure_http,
                allow_insecure_tls=allow_insecure_tls,
                ca_file=effective_ca_file,
                mtls_enabled=mtls_enabled,
                cert_file=effective_cert_file,
                key_file=effective_key_file,
            ),
            capabilities=capabilities_obj,
            storage_dir=storage,
            trust_profile=trust_profile,
            amqp_transport=amqp_transport,
            mqtt_transport=mqtt_transport,
            key_provider_info=key_provider_info,
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
    ) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any] | None]:
        shared_transports = self._shared_transports(remote_capabilities)
        direct_endpoint = identity_doc.get("service", {}).get("direct_endpoint")
        has_direct_endpoint = isinstance(direct_endpoint, str) and bool(direct_endpoint.strip())
        amqp_service = identity_doc.get("service", {}).get("amqp")
        amqp_service_valid = (
            isinstance(amqp_service, dict)
            and isinstance(amqp_service.get("broker_url"), str)
            and bool(str(amqp_service.get("broker_url")).strip())
        )
        amqp_available = "amqp" in shared_transports and amqp_service_valid
        mqtt_service = identity_doc.get("service", {}).get("mqtt")
        mqtt_service_valid = (
            isinstance(mqtt_service, dict)
            and isinstance(mqtt_service.get("broker_url"), str)
            and bool(str(mqtt_service.get("broker_url")).strip())
            and isinstance(mqtt_service.get("topic"), str)
            and bool(str(mqtt_service.get("topic")).strip())
        )
        mqtt_available = "mqtt" in shared_transports and mqtt_service_valid

        def _direct_available() -> bool:
            if not has_direct_endpoint:
                return False
            return any(transport in {"https", "http", "direct"} for transport in shared_transports)

        if delivery_mode == "direct":
            if _direct_available():
                return "direct", str(direct_endpoint), None, None
            return None, "No compatible direct transport and endpoint available", None, None

        if delivery_mode == "relay":
            if "relay" in shared_transports:
                return "relay", None, None, None
            return None, "No compatible relay transport available", None, None

        if delivery_mode == "amqp":
            if amqp_available:
                return "amqp", None, dict(amqp_service), None
            return None, "No compatible AMQP transport available", None, None

        if delivery_mode == "mqtt":
            if mqtt_available:
                return "mqtt", None, None, dict(mqtt_service)
            return None, "No compatible MQTT transport available", None, None

        for transport in shared_transports:
            if transport in {"https", "http", "direct"} and _direct_available():
                return "direct", str(direct_endpoint), None, None
            if transport == "relay":
                return "relay", None, None, None
            if transport == "amqp" and amqp_available:
                return "amqp", None, dict(amqp_service), None
            if transport == "mqtt" and mqtt_available:
                return "mqtt", None, None, dict(mqtt_service)

        if has_direct_endpoint:
            return None, "No compatible transport implementation available for this recipient", None, None
        if amqp_service_valid:
            return (
                None,
                "AMQP transport is advertised but not compatible with sender capabilities",
                None,
                None,
            )
        if mqtt_service_valid:
            return (
                None,
                "MQTT transport is advertised but not compatible with sender capabilities",
                None,
                None,
            )
        return (
            None,
            "Recipient identity document is missing direct_endpoint/amqp/mqtt and no relay fallback is compatible",
            None,
            None,
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

            delivery_channel, endpoint, amqp_service, mqtt_service = self._choose_delivery_channel(
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
                    amqp_service=amqp_service,
                    mqtt_service=mqtt_service,
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

    def _deliver_via_amqp(
        self,
        *,
        payload: dict[str, Any],
        message_class: MessageClass,
        context_id: str,
        operation_id: str,
        expires_in_seconds: int,
        correlation_id: str | None,
        in_reply_to: str | None,
        targets: list[ResolvedRecipient],
    ) -> tuple[list[DeliveryOutcome], list[str]]:
        outcomes: list[DeliveryOutcome] = []
        message_ids: list[str] = []

        if self.amqp_transport is None:
            for target in targets:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=(
                            "AMQP delivery selected but sender is not configured with AMQP broker settings"
                        ),
                    ),
                )
            return outcomes, message_ids

        for target in targets:
            outbound_message = self._build_message(
                recipients=[target.recipient],
                payload=payload,
                recipient_public_keys={target.recipient: target.public_key},
                message_class=message_class,
                context_id=context_id,
                operation_id=operation_id,
                expires_in_seconds=expires_in_seconds,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
            )
            message_ids.append(outbound_message.envelope.message_id)
            try:
                self.amqp_transport.publish(
                    message=outbound_message.to_dict(),
                    recipient_agent_id=target.recipient,
                    amqp_service=target.amqp_service,
                )
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.DELIVERED,
                    ),
                )
            except AMQPTransportError as exc:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=f"AMQP transport failure: {exc}",
                    ),
                )
        return outcomes, message_ids

    def _deliver_via_mqtt(
        self,
        *,
        payload: dict[str, Any],
        message_class: MessageClass,
        context_id: str,
        operation_id: str,
        expires_in_seconds: int,
        correlation_id: str | None,
        in_reply_to: str | None,
        targets: list[ResolvedRecipient],
    ) -> tuple[list[DeliveryOutcome], list[str]]:
        outcomes: list[DeliveryOutcome] = []
        message_ids: list[str] = []

        if self.mqtt_transport is None:
            for target in targets:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=(
                            "MQTT delivery selected but sender is not configured with MQTT broker settings"
                        ),
                    ),
                )
            return outcomes, message_ids

        for target in targets:
            outbound_message = self._build_message(
                recipients=[target.recipient],
                payload=payload,
                recipient_public_keys={target.recipient: target.public_key},
                message_class=message_class,
                context_id=context_id,
                operation_id=operation_id,
                expires_in_seconds=expires_in_seconds,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
            )
            message_ids.append(outbound_message.envelope.message_id)
            try:
                self.mqtt_transport.publish(
                    message=outbound_message.to_dict(),
                    recipient_agent_id=target.recipient,
                    mqtt_service=target.mqtt_service,
                )
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.DELIVERED,
                    ),
                )
            except MQTTTransportError as exc:
                outcomes.append(
                    DeliveryOutcome(
                        recipient=target.recipient,
                        state=DeliveryState.FAILED,
                        reason_code=FailReason.POLICY_REJECTED.value,
                        detail=f"MQTT transport failure: {exc}",
                    ),
                )
        return outcomes, message_ids

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
        if delivery_mode not in {"auto", "direct", "relay", "amqp", "mqtt"}:
            raise ValueError("delivery_mode must be one of: auto, direct, relay, amqp, mqtt")

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
        amqp_targets = [
            target for target in resolved_recipients if target.delivery_channel == "amqp"
        ]
        mqtt_targets = [
            target for target in resolved_recipients if target.delivery_channel == "mqtt"
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

        if amqp_targets:
            amqp_outcomes, amqp_message_ids = self._deliver_via_amqp(
                payload=payload,
                message_class=message_class,
                context_id=context_id,
                operation_id=operation_id,
                expires_in_seconds=expires_in_seconds,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
                targets=amqp_targets,
            )
            outbound_message_ids.extend(amqp_message_ids)
            outcomes.extend(amqp_outcomes)

        if mqtt_targets:
            mqtt_outcomes, mqtt_message_ids = self._deliver_via_mqtt(
                payload=payload,
                message_class=message_class,
                context_id=context_id,
                operation_id=operation_id,
                expires_in_seconds=expires_in_seconds,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
                targets=mqtt_targets,
            )
            outbound_message_ids.extend(mqtt_message_ids)
            outcomes.extend(mqtt_outcomes)

        if not outbound_message_ids:
            outbound_message_ids.append(str(uuid.uuid4()))

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

            if request_message.envelope.message_id in self._processed_message_ids:
                response_state = DeliveryState.ACKNOWLEDGED
                if request_message.envelope.message_class not in {
                    MessageClass.ACK,
                    MessageClass.FAIL,
                }:
                    response_message = self._create_response_message(
                        sender_identity_document=sender_identity_document,
                        request_envelope=request_message.envelope,
                        response_message_class=MessageClass.ACK,
                        response_payload=build_ack_payload(
                            request_message.envelope.message_id,
                            status="duplicate",
                        ),
                    )
                return {
                    "state": response_state.value,
                    "reason_code": reason_code,
                    "detail": detail,
                    "decrypted_payload": decrypted_payload,
                    "response_message": response_message.to_dict() if response_message else None,
                }

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
                if request_message.envelope.message_class not in {
                    MessageClass.ACK,
                    MessageClass.FAIL,
                }:
                    ack_payload = build_ack_payload(request_message.envelope.message_id)
                    if handler_payload:
                        ack_payload["handler"] = handler_payload
                    response_message = self._create_response_message(
                        sender_identity_document=sender_identity_document,
                        request_envelope=request_message.envelope,
                        response_message_class=MessageClass.ACK,
                        response_payload=ack_payload,
                    )
            self._processed_message_ids.add(request_message.envelope.message_id)
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

    def _publish_amqp_response_message(
        self,
        *,
        raw_message: dict[str, Any],
        response_message: dict[str, Any],
    ) -> None:
        if self.amqp_transport is None:
            raise AMQPTransportError("AMQP transport is not configured")
        envelope = raw_message.get("envelope")
        if not isinstance(envelope, dict):
            raise AMQPTransportError("Inbound message envelope is missing for AMQP response routing")
        sender_id = envelope.get("sender")
        if not isinstance(sender_id, str) or not sender_id.strip():
            raise AMQPTransportError("Inbound message sender is missing for AMQP response routing")

        sender_doc = self._resolve_sender_identity_document(
            raw_message=raw_message,
            sender_id=sender_id,
        )
        sender_service = sender_doc.get("service")
        sender_amqp_service = sender_service.get("amqp") if isinstance(sender_service, dict) else None
        if not isinstance(sender_amqp_service, dict):
            raise AMQPTransportError(
                f"Sender {sender_id} does not advertise service.amqp for AMQP response delivery",
            )

        self.amqp_transport.publish(
            message=response_message,
            recipient_agent_id=sender_id,
            amqp_service=sender_amqp_service,
        )

    def _publish_mqtt_response_message(
        self,
        *,
        raw_message: dict[str, Any],
        response_message: dict[str, Any],
    ) -> None:
        if self.mqtt_transport is None:
            raise MQTTTransportError("MQTT transport is not configured")
        envelope = raw_message.get("envelope")
        if not isinstance(envelope, dict):
            raise MQTTTransportError("Inbound message envelope is missing for MQTT response routing")
        sender_id = envelope.get("sender")
        if not isinstance(sender_id, str) or not sender_id.strip():
            raise MQTTTransportError("Inbound message sender is missing for MQTT response routing")

        sender_doc = self._resolve_sender_identity_document(
            raw_message=raw_message,
            sender_id=sender_id,
        )
        sender_service = sender_doc.get("service")
        sender_mqtt_service = sender_service.get("mqtt") if isinstance(sender_service, dict) else None
        if not isinstance(sender_mqtt_service, dict):
            raise MQTTTransportError(
                f"Sender {sender_id} does not advertise service.mqtt for MQTT response delivery",
            )

        self.mqtt_transport.publish(
            message=response_message,
            recipient_agent_id=sender_id,
            mqtt_service=sender_mqtt_service,
        )

    def consume_from_amqp(
        self,
        *,
        handler: IncomingHandler | None = None,
        max_messages: int | None = None,
    ) -> int:
        if self.amqp_transport is None:
            raise AMQPTransportError(
                "consume_from_amqp() requires an AMQP-configured agent (amqp_broker_url)",
            )

        service = self.identity_document.get("service", {})
        amqp_service = service.get("amqp") if isinstance(service, dict) else None
        if not isinstance(amqp_service, dict):
            raise AMQPTransportError("Identity document is missing service.amqp configuration")

        terminal_states = {
            DeliveryState.ACKNOWLEDGED.value,
            DeliveryState.FAILED.value,
            DeliveryState.DECLINED.value,
            DeliveryState.EXPIRED.value,
        }

        def _handle(raw_message: dict[str, Any]) -> bool:
            result = self.handle_incoming(raw_message, handler=handler)
            response_message = result.get("response_message")
            if isinstance(response_message, dict):
                try:
                    self._publish_amqp_response_message(
                        raw_message=raw_message,
                        response_message=response_message,
                    )
                except Exception:  # noqa: BLE001
                    return False
            return result.get("state") in terminal_states

        return self.amqp_transport.consume(
            agent_id=self.agent_id,
            handler=_handle,
            amqp_service=amqp_service,
            max_messages=max_messages,
        )

    def consume_from_mqtt(
        self,
        *,
        handler: IncomingHandler | None = None,
        max_messages: int | None = None,
    ) -> int:
        if self.mqtt_transport is None:
            raise MQTTTransportError(
                "consume_from_mqtt() requires an MQTT-configured agent (mqtt_broker_url)",
            )

        service = self.identity_document.get("service", {})
        mqtt_service = service.get("mqtt") if isinstance(service, dict) else None
        if not isinstance(mqtt_service, dict):
            raise MQTTTransportError("Identity document is missing service.mqtt configuration")

        terminal_states = {
            DeliveryState.ACKNOWLEDGED.value,
            DeliveryState.FAILED.value,
            DeliveryState.DECLINED.value,
            DeliveryState.EXPIRED.value,
        }

        def _handle(raw_message: dict[str, Any]) -> bool:
            result = self.handle_incoming(raw_message, handler=handler)
            response_message = result.get("response_message")
            if isinstance(response_message, dict):
                try:
                    self._publish_mqtt_response_message(
                        raw_message=raw_message,
                        response_message=response_message,
                    )
                except Exception:  # noqa: BLE001
                    return False
            return result.get("state") in terminal_states

        return self.mqtt_transport.consume(
            agent_id=self.agent_id,
            handler=_handle,
            mqtt_service=mqtt_service,
            max_messages=max_messages,
        )

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
