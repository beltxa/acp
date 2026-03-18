/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class AcpAgent {
    private static final String DEFAULT_IDENTITY_DOCUMENT_PATH = "/api/v1/acp/identity";

    private final AgentIdentity identity;
    private final Map<String, Object> identityDocument;
    private final DiscoveryClient discovery;
    private final TransportClient transport;
    private final AmqpTransportClient amqpTransport;
    private final MqttTransportClient mqttTransport;
    private final AgentCapabilities capabilities;
    private final Path storageDir;
    private final String trustProfile;
    private final String relayUrl;
    private final DedupStore dedupStore;
    private final DeliveryMode defaultDeliveryMode;
    private final Map<String, Object> keyProviderInfo;
    private final Map<String, Map<String, String>> deliveryStates = new ConcurrentHashMap<>();

    private AcpAgent(
        AgentIdentity identity,
        Map<String, Object> identityDocument,
        DiscoveryClient discovery,
        TransportClient transport,
        AmqpTransportClient amqpTransport,
        MqttTransportClient mqttTransport,
        AgentCapabilities capabilities,
        Path storageDir,
        String trustProfile,
        String relayUrl,
        DeliveryMode defaultDeliveryMode,
        Map<String, Object> keyProviderInfo
    ) {
        this.identity = identity;
        this.identityDocument = identityDocument;
        this.discovery = discovery;
        this.transport = transport;
        this.amqpTransport = amqpTransport;
        this.mqttTransport = mqttTransport;
        this.capabilities = capabilities;
        this.storageDir = storageDir;
        this.trustProfile = trustProfile;
        this.relayUrl = relayUrl;
        this.defaultDeliveryMode = defaultDeliveryMode == null ? DeliveryMode.AUTO : defaultDeliveryMode;
        this.keyProviderInfo = keyProviderInfo == null ? Map.of() : Map.copyOf(keyProviderInfo);
        this.dedupStore = new DedupStore(Duration.ofHours(1));
    }

    public static AcpAgent loadOrCreate(String agentId) {
        return loadOrCreate(agentId, new AcpAgentOptions());
    }

    public static AcpAgent loadOrCreate(String agentId, AcpAgentOptions options) {
        Objects.requireNonNull(agentId, "agentId must be provided");
        AgentIdentity.parseAgentId(agentId);
        AcpAgentOptions effective = options == null ? new AcpAgentOptions() : options;

        Path storage = effective.getStorageDir();
        try {
            Files.createDirectories(storage);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to create storage directory " + storage, exc);
        }

        KeyProvider keyProvider = resolveKeyProvider(effective, storage);
        Map<String, Object> keyProviderInfo;
        try {
            keyProviderInfo = keyProvider.describe();
            if (keyProviderInfo == null) {
                keyProviderInfo = Map.of("provider", "unknown");
            }
        } catch (Exception exc) {
            keyProviderInfo = Map.of("provider", "unknown");
        }

        TlsMaterial providerTlsMaterial = null;
        String providerCaBundle = null;
        try {
            providerTlsMaterial = keyProvider.loadTlsMaterial(agentId);
        } catch (KeyProviderException exc) {
            if (effective.isMtlsEnabled()) {
                throw new IllegalStateException("Unable to load TLS material from key provider: " + exc.getMessage(), exc);
            }
        }
        try {
            providerCaBundle = keyProvider.loadCaBundle(agentId);
        } catch (KeyProviderException ignored) {
            providerCaBundle = null;
        }

        String effectiveCaFile = firstNonBlank(
            effective.getCaFile(),
            providerTlsMaterial == null ? null : providerTlsMaterial.getCaFile(),
            providerCaBundle
        );
        String effectiveCertFile = firstNonBlank(
            effective.getCertFile(),
            providerTlsMaterial == null ? null : providerTlsMaterial.getCertFile()
        );
        String effectiveKeyFile = firstNonBlank(
            effective.getKeyFile(),
            providerTlsMaterial == null ? null : providerTlsMaterial.getKeyFile()
        );

        HttpSecurity.validateHttpClientPolicy(
            effective.isAllowInsecureTls(),
            effectiveCaFile,
            effective.isMtlsEnabled(),
            effectiveCertFile,
            effectiveKeyFile,
            "Agent HTTP security configuration"
        );

        if (effective.getEndpoint() != null && !effective.getEndpoint().isBlank()) {
            HttpSecurity.validateHttpUrl(
                effective.getEndpoint(),
                effective.isAllowInsecureHttp(),
                effective.isMtlsEnabled(),
                "Agent direct endpoint configuration"
            );
        }
        if (effective.getRelayUrl() != null && !effective.getRelayUrl().isBlank()) {
            HttpSecurity.validateHttpUrl(
                effective.getRelayUrl(),
                effective.isAllowInsecureHttp(),
                effective.isMtlsEnabled(),
                "Agent relay URL configuration"
            );
        }
        for (String hint : effective.getRelayHints()) {
            if (hint != null && !hint.isBlank()) {
                HttpSecurity.validateHttpUrl(
                    hint,
                    effective.isAllowInsecureHttp(),
                    effective.isMtlsEnabled(),
                    "Agent relay hint configuration"
                );
            }
        }
        for (String hint : effective.getEnterpriseDirectoryHints()) {
            if (hint != null && !hint.isBlank()) {
                HttpSecurity.validateHttpUrl(
                    hint,
                    effective.isAllowInsecureHttp(),
                    effective.isMtlsEnabled(),
                    "Agent enterprise directory hint configuration"
                );
            }
        }

        AgentIdentity identity;
        Map<String, Object> identityDocument;
        AgentIdentity.IdentityBundle existing = AgentIdentity.readIdentity(storage, agentId);
        AgentCapabilities capabilities;
        Map<String, Object> localAmqpService = buildLocalAmqpService(agentId, effective);
        Map<String, Object> localMqttService = buildLocalMqttService(agentId, effective);
        IdentityKeyMaterial providerIdentityKeys = null;
        KeyProviderException providerIdentityError = null;
        try {
            providerIdentityKeys = keyProvider.loadIdentityKeys(agentId);
        } catch (KeyProviderException exc) {
            providerIdentityError = exc;
        }
        boolean externalKeyProvider = isExternalKeyProvider(keyProvider);

        if (existing == null) {
            if (providerIdentityKeys != null) {
                identity = identityFromProvider(agentId, providerIdentityKeys);
            } else if (externalKeyProvider) {
                throw new IllegalStateException(
                    "Unable to load identity keys from key provider: "
                        + (providerIdentityError == null ? "unknown error" : providerIdentityError.getMessage()),
                    providerIdentityError
                );
            } else {
                identity = AgentIdentity.create(agentId);
            }
            capabilities = effective.getCapabilities() == null
                ? new AgentCapabilities(agentId)
                : effective.getCapabilities();
            identityDocument = identity.buildIdentityDocument(
                effective.getEndpoint(),
                effective.getRelayHints(),
                effective.getTrustProfile(),
                capabilities.toMap(),
                365,
                localAmqpService,
                localMqttService
            );
            applyHttpSecurityProfile(identityDocument, effective.isMtlsEnabled());
            AgentIdentity.writeIdentity(storage, identity, identityDocument);
        } else {
            identity = existing.identity();
            identityDocument = existing.identityDocument();
            if (providerIdentityKeys != null) {
                identity = applyProviderKeys(identity, providerIdentityKeys);
            } else if (externalKeyProvider) {
                throw new IllegalStateException(
                    "Unable to load identity keys from key provider: "
                        + (providerIdentityError == null ? "unknown error" : providerIdentityError.getMessage()),
                    providerIdentityError
                );
            }
            boolean validDocument = AgentIdentity.verifyIdentityDocument(identityDocument);
            capabilities = effective.getCapabilities() != null
                ? effective.getCapabilities()
                : AgentCapabilities.fromMap(asMap(identityDocument.get("capabilities")), agentId);

            boolean shouldRewrite = !validDocument
                || effective.getEndpoint() != null
                || (effective.getRelayHints() != null && !effective.getRelayHints().isEmpty())
                || effective.getCapabilities() != null
                || localAmqpService != null
                || localMqttService != null;
            if (shouldRewrite) {
                String existingEndpoint = asString(asMap(identityDocument.get("service")).get("direct_endpoint"));
                List<String> existingHints = asStringList(asMap(identityDocument.get("service")).get("relay_hints"));
                Map<String, Object> existingAmqpService = asMap(asMap(identityDocument.get("service")).get("amqp"));
                Map<String, Object> existingMqttService = asMap(asMap(identityDocument.get("service")).get("mqtt"));
                identityDocument = identity.buildIdentityDocument(
                    effective.getEndpoint() != null ? effective.getEndpoint() : existingEndpoint,
                    effective.getRelayHints() != null && !effective.getRelayHints().isEmpty()
                        ? effective.getRelayHints()
                        : existingHints,
                    effective.getTrustProfile(),
                    capabilities.toMap(),
                    365,
                    localAmqpService != null ? localAmqpService : existingAmqpService,
                    localMqttService != null ? localMqttService : existingMqttService
                );
                applyHttpSecurityProfile(identityDocument, effective.isMtlsEnabled());
                AgentIdentity.writeIdentity(storage, identity, identityDocument);
            }
        }

        List<String> effectiveRelayHints = new ArrayList<>();
        if (effective.getRelayHints() != null && !effective.getRelayHints().isEmpty()) {
            effectiveRelayHints.addAll(effective.getRelayHints());
        } else {
            effectiveRelayHints.addAll(asStringList(asMap(identityDocument.get("service")).get("relay_hints")));
        }
        if (effective.getRelayUrl() != null
            && !effective.getRelayUrl().isBlank()
            && !effectiveRelayHints.contains(effective.getRelayUrl())) {
            effectiveRelayHints.add(effective.getRelayUrl());
        }

        DiscoveryClient discovery = new DiscoveryClient(
            storage.resolve("discovery_cache.json"),
            effective.getDiscoveryScheme(),
            effectiveRelayHints,
            effective.getEnterpriseDirectoryHints(),
            effective.getHttpTimeoutSeconds(),
            effective.isAllowInsecureHttp(),
            effective.isAllowInsecureTls(),
            effectiveCaFile,
            effective.isMtlsEnabled(),
            effectiveCertFile,
            effectiveKeyFile
        );
        discovery.seed(identityDocument);

        AmqpTransportClient amqpTransport = effective.getAmqpTransport();
        if (amqpTransport == null && effective.getAmqpBrokerUrl() != null && !effective.getAmqpBrokerUrl().isBlank()) {
            amqpTransport = new AmqpTransportClient(
                effective.getAmqpBrokerUrl(),
                effective.getAmqpExchange(),
                effective.getAmqpExchangeType(),
                effective.getHttpTimeoutSeconds()
            );
        }

        MqttTransportClient mqttTransport = effective.getMqttTransport();
        if (mqttTransport == null && effective.getMqttBrokerUrl() != null && !effective.getMqttBrokerUrl().isBlank()) {
            mqttTransport = new MqttTransportClient(
                effective.getMqttBrokerUrl(),
                effective.getMqttQos(),
                effective.getMqttTopicPrefix(),
                effective.getHttpTimeoutSeconds(),
                30
            );
        }

        return new AcpAgent(
            identity,
            identityDocument,
            discovery,
            new TransportClient(
                effective.getHttpTimeoutSeconds(),
                effective.isAllowInsecureHttp(),
                effective.isAllowInsecureTls(),
                effectiveCaFile,
                effective.isMtlsEnabled(),
                effectiveCertFile,
                effectiveKeyFile
            ),
            amqpTransport,
            mqttTransport,
            capabilities,
            storage,
            effective.getTrustProfile(),
            effective.getRelayUrl(),
            effective.getDefaultDeliveryMode(),
            keyProviderInfo
        );
    }

    public String getAgentId() {
        return identity.getAgentId();
    }

    public Map<String, Object> getIdentityDocument() {
        return identityDocument;
    }

    public Map<String, Object> buildWellKnownDocument(String baseUrl) {
        return buildWellKnownDocument(baseUrl, null);
    }

    public Map<String, Object> buildWellKnownDocument(String baseUrl, String identityDocumentUrl) {
        String resolvedBaseUrl = !isBlank(baseUrl)
            ? baseUrl
            : baseUrlFromEndpoint(asString(asMap(identityDocument.get("service")).get("direct_endpoint")));
        if (isBlank(resolvedBaseUrl)) {
            throw new IllegalStateException(
                "Unable to build /.well-known/acp metadata without baseUrl or direct_endpoint"
            );
        }

        Map<String, Object> service = asMap(identityDocument.get("service"));
        Map<String, Object> transports = new LinkedHashMap<>();

        String directEndpoint = asString(service.get("direct_endpoint"));
        if (!isBlank(directEndpoint)) {
            Map<String, Object> http = new LinkedHashMap<>();
            http.put("endpoint", directEndpoint);
            String httpSecurityProfile = asString(asMap(service.get("http")).get("security_profile"));
            if (!isBlank(httpSecurityProfile)) {
                http.put("security_profile", httpSecurityProfile);
            }
            transports.put("http", http);
        }

        List<String> relayHints = asStringList(service.get("relay_hints"));
        if (!relayHints.isEmpty()) {
            Map<String, Object> relay = new LinkedHashMap<>();
            relay.put("endpoint", relayHints.get(0));
            String relaySecurityProfile = asString(asMap(service.get("relay")).get("security_profile"));
            if (!isBlank(relaySecurityProfile)) {
                relay.put("security_profile", relaySecurityProfile);
            }
            if (relayHints.size() > 1) {
                relay.put("hints", relayHints);
            }
            transports.put("relay", relay);
        }

        Map<String, Object> amqp = asMap(service.get("amqp"));
        if (!amqp.isEmpty()) {
            transports.put("amqp", new LinkedHashMap<>(amqp));
        }
        Map<String, Object> mqtt = asMap(service.get("mqtt"));
        if (!mqtt.isEmpty()) {
            transports.put("mqtt", new LinkedHashMap<>(mqtt));
        }

        Map<String, Object> wellKnown = new LinkedHashMap<>();
        wellKnown.put("agent_id", asString(identityDocument.get("agent_id")));
        wellKnown.put(
            "identity_document",
            !isBlank(identityDocumentUrl)
                ? identityDocumentUrl
                : normalizedBaseUrl(resolvedBaseUrl) + DEFAULT_IDENTITY_DOCUMENT_PATH
        );
        wellKnown.put("transports", transports);
        wellKnown.put("version", AcpConstants.ACP_VERSION);
        wellKnown.put("security_profile", inferWellKnownSecurityProfile(transports));

        Map<String, Object> supports = asMap(asMap(identityDocument.get("capabilities")).get("supports"));
        if (!supports.isEmpty()) {
            List<String> capabilitiesList = new ArrayList<>();
            for (Map.Entry<String, Object> entry : supports.entrySet()) {
                if (entry.getValue() instanceof Boolean enabled && enabled) {
                    capabilitiesList.add(entry.getKey());
                }
            }
            capabilitiesList.sort(String::compareTo);
            wellKnown.put("capabilities", capabilitiesList);
        }
        return wellKnown;
    }

    public Map<String, Object> getKeyProviderInfo() {
        return keyProviderInfo;
    }

    public void registerIdentityDocument(Map<String, Object> identityDocument) {
        discovery.registerIdentityDocument(identityDocument);
    }

    public Map<String, Object> resolveWellKnown(String baseUrl, String expectedAgentId) {
        return discovery.resolveWellKnown(baseUrl, expectedAgentId);
    }

    public SendResult send(List<String> recipients, Map<String, Object> payload, String context) {
        return send(
            recipients,
            payload,
            context,
            MessageClass.SEND,
            300,
            null,
            null,
            defaultDeliveryMode
        );
    }

    public SendResult send(
        List<String> recipients,
        Map<String, Object> payload,
        String context,
        DeliveryMode deliveryMode
    ) {
        return send(
            recipients,
            payload,
            context,
            MessageClass.SEND,
            300,
            null,
            null,
            deliveryMode
        );
    }

    public SendResult sendCompensate(
        List<String> recipients,
        String originalOperationId,
        String reason,
        List<Map<String, Object>> actions,
        String context,
        DeliveryMode deliveryMode
    ) {
        CompensateInstruction instruction = new CompensateInstruction(
            originalOperationId,
            reason,
            actions == null ? List.of() : actions
        );
        return send(
            recipients,
            Map.of("compensation", instruction.toMap()),
            context == null ? "compensate:" + originalOperationId : context,
            MessageClass.COMPENSATE,
            300,
            originalOperationId,
            null,
            deliveryMode
        );
    }

    public SendResult send(
        List<String> recipients,
        Map<String, Object> payload,
        String context,
        MessageClass messageClass,
        int expiresInSeconds,
        String correlationId,
        String inReplyTo,
        DeliveryMode deliveryMode
    ) {
        if (recipients == null || recipients.isEmpty()) {
            throw new IllegalArgumentException("send() requires at least one recipient");
        }
        DeliveryMode mode = deliveryMode == null ? DeliveryMode.AUTO : deliveryMode;
        String operationId = UUID.randomUUID().toString();
        String contextId = context == null ? operationId : context;

        ResolvedRecipients resolved = resolveRecipients(recipients, mode);
        if (resolved.deliverable().isEmpty()) {
            SendResult result = new SendResult();
            result.setOperationId(operationId);
            result.setMessageId(UUID.randomUUID().toString());
            result.setOutcomes(resolved.preflightOutcomes());
            syncDeliveryStates(operationId, resolved.preflightOutcomes());
            return result;
        }

        List<DeliveryOutcome> outcomes = new ArrayList<>(resolved.preflightOutcomes());
        List<String> messageIds = new ArrayList<>();

        List<ResolvedRecipient> directTargets = resolved.deliverable().stream()
            .filter(target -> "direct".equals(target.channel()))
            .toList();
        List<ResolvedRecipient> relayTargets = resolved.deliverable().stream()
            .filter(target -> "relay".equals(target.channel()))
            .toList();
        List<ResolvedRecipient> amqpTargets = resolved.deliverable().stream()
            .filter(target -> "amqp".equals(target.channel()))
            .toList();
        List<ResolvedRecipient> mqttTargets = resolved.deliverable().stream()
            .filter(target -> "mqtt".equals(target.channel()))
            .toList();

        if (!directTargets.isEmpty()) {
            AcpMessage directMessage = buildMessage(
                directTargets.stream().map(ResolvedRecipient::recipient).toList(),
                payload,
                toPublicKeyMap(directTargets),
                messageClass,
                contextId,
                operationId,
                expiresInSeconds,
                correlationId,
                inReplyTo
            );
            messageIds.add(directMessage.getEnvelope().getMessageId());
            outcomes.addAll(deliverDirect(directMessage, directTargets));
        }

        if (!relayTargets.isEmpty()) {
            AcpMessage relayMessage = buildMessage(
                relayTargets.stream().map(ResolvedRecipient::recipient).toList(),
                payload,
                toPublicKeyMap(relayTargets),
                messageClass,
                contextId,
                operationId,
                expiresInSeconds,
                correlationId,
                inReplyTo
            );
            messageIds.add(relayMessage.getEnvelope().getMessageId());
            outcomes.addAll(deliverViaRelay(relayMessage, relayTargets));
        }

        if (!amqpTargets.isEmpty()) {
            for (ResolvedRecipient target : amqpTargets) {
                AcpMessage amqpMessage = buildMessage(
                    List.of(target.recipient()),
                    payload,
                    Map.of(target.recipient(), target.publicKey()),
                    messageClass,
                    contextId,
                    operationId,
                    expiresInSeconds,
                    correlationId,
                    inReplyTo
                );
                messageIds.add(amqpMessage.getEnvelope().getMessageId());
                outcomes.add(deliverViaAmqp(amqpMessage, target));
            }
        }

        if (!mqttTargets.isEmpty()) {
            for (ResolvedRecipient target : mqttTargets) {
                AcpMessage mqttMessage = buildMessage(
                    List.of(target.recipient()),
                    payload,
                    Map.of(target.recipient(), target.publicKey()),
                    messageClass,
                    contextId,
                    operationId,
                    expiresInSeconds,
                    correlationId,
                    inReplyTo
                );
                messageIds.add(mqttMessage.getEnvelope().getMessageId());
                outcomes.add(deliverViaMqtt(mqttMessage, target));
            }
        }

        if (messageIds.isEmpty()) {
            messageIds.add(UUID.randomUUID().toString());
        }

        SendResult result = new SendResult();
        result.setOperationId(operationId);
        result.setMessageId(messageIds.get(0));
        result.setMessageIds(messageIds);
        result.setOutcomes(outcomes);
        syncDeliveryStates(operationId, outcomes);
        return result;
    }

    public DecryptedMessage decryptMessageForSelf(Map<String, Object> rawMessage) {
        AcpMessage message = AcpMessage.fromMap(rawMessage);
        validateEnvelopeForInbound(message.getEnvelope());
        if (message.getEnvelope().getRecipients() == null
            || !message.getEnvelope().getRecipients().contains(getAgentId())) {
            throw new ProcessingException(FailReason.POLICY_REJECTED, "Message is not addressed to this agent");
        }
        Map<String, Object> senderDoc = resolveSenderIdentityDocument(rawMessage, message.getEnvelope().getSender());
        String senderSigningKey = asString(asMap(asMap(senderDoc.get("keys")).get("signing")).get("public_key"));
        if (senderSigningKey == null) {
            throw new ProcessingException(FailReason.INVALID_SIGNATURE, "Sender signing public key missing");
        }
        if (!CryptoSupport.verifyProtectedPayloadSignature(
            message.getEnvelope(),
            message.getProtectedPayload(),
            senderSigningKey
        )) {
            throw new ProcessingException(FailReason.INVALID_SIGNATURE, "Message signature verification failed");
        }
        Map<String, Object> payload = CryptoSupport.decryptForRecipient(
            message.getEnvelope(),
            message.getProtectedPayload(),
            getAgentId(),
            identity.getEncryptionPrivateKey()
        );
        return new DecryptedMessage(message, payload);
    }

    public InboundResult receive(String rawMessageJson) {
        return receive(rawMessageJson, null);
    }

    public InboundResult receive(String rawMessageJson, InboundHandler handler) {
        Map<String, Object> rawMessage = JsonSupport.mapFromJson(rawMessageJson);
        return receive(rawMessage, handler);
    }

    public InboundResult receive(Map<String, Object> rawMessage, InboundHandler handler) {
        InboundResult result = new InboundResult();
        result.setState(DeliveryState.FAILED);

        AcpMessage requestMessage;
        try {
            requestMessage = AcpMessage.fromMap(rawMessage);
        } catch (Exception exc) {
            result.setReasonCode(FailReason.POLICY_REJECTED.name());
            result.setDetail("Invalid ACP message structure: " + exc.getMessage());
            return result;
        }

        Map<String, Object> senderIdentityDocument = null;
        try {
            validateEnvelopeForInbound(requestMessage.getEnvelope());
            if (requestMessage.getEnvelope().getRecipients() == null
                || !requestMessage.getEnvelope().getRecipients().contains(getAgentId())) {
                throw new ProcessingException(
                    FailReason.POLICY_REJECTED,
                    "Recipient " + getAgentId() + " not in message recipients"
                );
            }

            senderIdentityDocument = resolveSenderIdentityDocument(rawMessage, requestMessage.getEnvelope().getSender());
            String senderSigningKey = asString(asMap(asMap(senderIdentityDocument.get("keys")).get("signing")).get("public_key"));
            if (senderSigningKey == null) {
                throw new ProcessingException(FailReason.INVALID_SIGNATURE, "Sender signing key missing from identity document");
            }

            if (!CryptoSupport.verifyProtectedPayloadSignature(
                requestMessage.getEnvelope(),
                requestMessage.getProtectedPayload(),
                senderSigningKey
            )) {
                throw new ProcessingException(FailReason.INVALID_SIGNATURE, "Signature verification failed");
            }

            if (dedupStore.isDuplicate(requestMessage.getEnvelope().getMessageId())) {
                result.setState(DeliveryState.ACKNOWLEDGED);
                result.setDetail("Duplicate message acknowledged");
                if (requestMessage.getEnvelope().getMessageClass() != MessageClass.ACK
                    && requestMessage.getEnvelope().getMessageClass() != MessageClass.FAIL) {
                    AcpMessage duplicateAck = createResponseMessage(
                        senderIdentityDocument,
                        requestMessage.getEnvelope(),
                        MessageClass.ACK,
                        buildAckPayload(requestMessage.getEnvelope().getMessageId(), "duplicate")
                    );
                    result.setResponseMessage(duplicateAck.toMap());
                }
                return result;
            }

            Map<String, Object> decryptedPayload = CryptoSupport.decryptForRecipient(
                requestMessage.getEnvelope(),
                requestMessage.getProtectedPayload(),
                getAgentId(),
                identity.getEncryptionPrivateKey()
            );
            result.setDecryptedPayload(decryptedPayload);

            AcpMessage responseMessage;
            if (requestMessage.getEnvelope().getMessageClass() == MessageClass.CAPABILITIES) {
                responseMessage = createResponseMessage(
                    senderIdentityDocument,
                    requestMessage.getEnvelope(),
                    MessageClass.CAPABILITIES,
                    capabilities.toMap()
                );
            } else {
                Map<String, Object> ackPayload = buildAckPayload(requestMessage.getEnvelope().getMessageId(), "accepted");
                if (handler != null) {
                    Map<String, Object> handlerPayload = handler.handle(decryptedPayload, requestMessage.getEnvelope());
                    if (handlerPayload != null && !handlerPayload.isEmpty()) {
                        ackPayload.put("handler", handlerPayload);
                    }
                }
                if (requestMessage.getEnvelope().getMessageClass() == MessageClass.ACK
                    || requestMessage.getEnvelope().getMessageClass() == MessageClass.FAIL) {
                    responseMessage = null;
                } else {
                    responseMessage = createResponseMessage(
                        senderIdentityDocument,
                        requestMessage.getEnvelope(),
                        MessageClass.ACK,
                        ackPayload
                    );
                }
            }
            dedupStore.markProcessed(requestMessage.getEnvelope().getMessageId());
            result.setState(DeliveryState.ACKNOWLEDGED);
            result.setResponseMessage(responseMessage == null ? null : responseMessage.toMap());
            return result;
        } catch (ProcessingException exc) {
            result.setReasonCode(exc.getReasonCode().name());
            result.setDetail(exc.getMessage());
        } catch (Exception exc) {
            result.setReasonCode(FailReason.POLICY_REJECTED.name());
            result.setDetail(exc.getMessage());
        }

        if (senderIdentityDocument != null) {
            try {
                String reasonCode = result.getReasonCode() == null ? FailReason.POLICY_REJECTED.name() : result.getReasonCode();
                String detail = result.getDetail() == null ? "Message processing failed" : result.getDetail();
                AcpMessage failMessage = createResponseMessage(
                    senderIdentityDocument,
                    requestMessage.getEnvelope(),
                    MessageClass.FAIL,
                    buildFailPayload(reasonCode, detail, false)
                );
                result.setResponseMessage(failMessage.toMap());
            } catch (Exception ignored) {
                result.setResponseMessage(null);
            }
        }
        return result;
    }

    public CapabilityRequestResult requestCapabilities(String recipient) {
        SendResult result = send(
            List.of(recipient),
            Map.of("request", "capabilities"),
            "capabilities:" + UUID.randomUUID(),
            MessageClass.CAPABILITIES,
            300,
            null,
            null,
            defaultDeliveryMode
        );

        Map<String, Object> responsePayload = null;
        for (DeliveryOutcome outcome : result.getOutcomes()) {
            if (outcome.getResponseMessage() == null) {
                continue;
            }
            try {
                DecryptedMessage decrypted = decryptMessageForSelf(outcome.getResponseMessage());
                if (decrypted.message().getEnvelope().getMessageClass() == MessageClass.CAPABILITIES) {
                    responsePayload = decrypted.payload();
                    break;
                }
            } catch (Exception ignored) {
                // Try next outcome.
            }
        }
        return new CapabilityRequestResult(result, responsePayload);
    }

    public int consumeFromAmqp(int maxMessages) {
        return consumeFromAmqp(maxMessages, null);
    }

    public int consumeFromAmqp(int maxMessages, InboundHandler handler) {
        if (amqpTransport == null) {
            throw new IllegalStateException(
                "consumeFromAmqp() requires an AMQP-configured agent (AcpAgentOptions.setAmqpBrokerUrl)"
            );
        }
        Map<String, Object> amqpService = asMap(asMap(identityDocument.get("service")).get("amqp"));
        if (amqpService.isEmpty()) {
            throw new IllegalStateException("Identity document is missing service.amqp configuration");
        }
        return amqpTransport.consume(
            getAgentId(),
            rawMessage -> {
                InboundResult inbound = receive(rawMessage, handler);
                if (inbound.getResponseMessage() != null && !inbound.getResponseMessage().isEmpty()) {
                    try {
                        publishAmqpResponseMessage(rawMessage, inbound.getResponseMessage());
                    } catch (Exception exc) {
                        return false;
                    }
                }
                return inbound.getState() == DeliveryState.ACKNOWLEDGED
                    || inbound.getState() == DeliveryState.FAILED
                    || inbound.getState() == DeliveryState.DECLINED
                    || inbound.getState() == DeliveryState.EXPIRED;
            },
            amqpService,
            maxMessages
        );
    }

    public int consumeFromMqtt(int maxMessages) {
        return consumeFromMqtt(maxMessages, null);
    }

    public int consumeFromMqtt(int maxMessages, InboundHandler handler) {
        if (mqttTransport == null) {
            throw new IllegalStateException(
                "consumeFromMqtt() requires an MQTT-configured agent (AcpAgentOptions.setMqttBrokerUrl)"
            );
        }
        Map<String, Object> mqttService = asMap(asMap(identityDocument.get("service")).get("mqtt"));
        if (mqttService.isEmpty()) {
            throw new IllegalStateException("Identity document is missing service.mqtt configuration");
        }
        return mqttTransport.consume(
            getAgentId(),
            rawMessage -> {
                InboundResult inbound = receive(rawMessage, handler);
                if (inbound.getResponseMessage() != null && !inbound.getResponseMessage().isEmpty()) {
                    try {
                        publishMqttResponseMessage(rawMessage, inbound.getResponseMessage());
                    } catch (Exception exc) {
                        return false;
                    }
                }
                return inbound.getState() == DeliveryState.ACKNOWLEDGED
                    || inbound.getState() == DeliveryState.FAILED
                    || inbound.getState() == DeliveryState.DECLINED
                    || inbound.getState() == DeliveryState.EXPIRED;
            },
            mqttService,
            maxMessages
        );
    }

    private void publishAmqpResponseMessage(
        Map<String, Object> rawMessage,
        Map<String, Object> responseMessage
    ) {
        if (amqpTransport == null) {
            throw new IllegalStateException("AMQP transport is not configured");
        }
        String senderId = asString(asMap(rawMessage.get("envelope")).get("sender"));
        if (isBlank(senderId)) {
            throw new IllegalStateException("Inbound message sender is missing for AMQP response routing");
        }
        Map<String, Object> senderIdentity = resolveSenderIdentityDocument(rawMessage, senderId);
        Map<String, Object> senderAmqpService = asMap(asMap(senderIdentity.get("service")).get("amqp"));
        if (senderAmqpService.isEmpty()) {
            throw new IllegalStateException(
                "Sender " + senderId + " does not advertise service.amqp for AMQP response delivery"
            );
        }
        amqpTransport.publish(responseMessage, senderId, senderAmqpService);
    }

    private void publishMqttResponseMessage(
        Map<String, Object> rawMessage,
        Map<String, Object> responseMessage
    ) {
        if (mqttTransport == null) {
            throw new IllegalStateException("MQTT transport is not configured");
        }
        String senderId = asString(asMap(rawMessage.get("envelope")).get("sender"));
        if (isBlank(senderId)) {
            throw new IllegalStateException("Inbound message sender is missing for MQTT response routing");
        }
        Map<String, Object> senderIdentity = resolveSenderIdentityDocument(rawMessage, senderId);
        Map<String, Object> senderMqttService = asMap(asMap(senderIdentity.get("service")).get("mqtt"));
        if (senderMqttService.isEmpty()) {
            throw new IllegalStateException(
                "Sender " + senderId + " does not advertise service.mqtt for MQTT response delivery"
            );
        }
        mqttTransport.publish(responseMessage, senderId, senderMqttService);
    }

    public Map<String, Map<String, String>> getDeliveryStates() {
        return deliveryStates;
    }

    public Path getStorageDir() {
        return storageDir;
    }

    public String getTrustProfile() {
        return trustProfile;
    }

    public AgentCapabilities getCapabilities() {
        return capabilities;
    }

    private ResolvedRecipients resolveRecipients(List<String> recipients, DeliveryMode mode) {
        List<ResolvedRecipient> resolved = new ArrayList<>();
        List<DeliveryOutcome> outcomes = new ArrayList<>();

        for (String recipient : recipients) {
            Map<String, Object> identityDoc;
            try {
                identityDoc = discovery.resolve(recipient);
            } catch (Exception exc) {
                outcomes.add(failedOutcome(recipient, FailReason.POLICY_REJECTED.name(), exc.getMessage()));
                continue;
            }

            AgentCapabilities remoteCapabilities = AgentCapabilities.fromMap(asMap(identityDoc.get("capabilities")), recipient);
            AgentCapabilities.CapabilityMatch match = capabilities.chooseCompatible(remoteCapabilities);
            if (!match.isCompatible()) {
                outcomes.add(failedOutcome(recipient, reasonForCapabilityMismatch(match.getReason()).name(), match.getReason()));
                continue;
            }

            ChannelChoice choice = chooseDeliveryChannel(remoteCapabilities, identityDoc, mode);
            if (choice.channel() == null) {
                outcomes.add(failedOutcome(recipient, FailReason.POLICY_REJECTED.name(), choice.detail()));
                continue;
            }

            String recipientPublicKey = asString(
                asMap(asMap(identityDoc.get("keys")).get("encryption")).get("public_key")
            );
            if (recipientPublicKey == null || recipientPublicKey.isBlank()) {
                outcomes.add(failedOutcome(
                    recipient,
                    FailReason.POLICY_REJECTED.name(),
                    "Recipient identity document missing encryption public key"
                ));
                continue;
            }

            resolved.add(new ResolvedRecipient(
                recipient,
                recipientPublicKey,
                identityDoc,
                choice.channel(),
                choice.endpoint(),
                choice.amqpService(),
                choice.mqttService()
            ));
        }
        return new ResolvedRecipients(resolved, outcomes);
    }

    private ChannelChoice chooseDeliveryChannel(
        AgentCapabilities remoteCapabilities,
        Map<String, Object> identityDocument,
        DeliveryMode mode
    ) {
        Set<String> remoteTransports = Set.copyOf(
            remoteCapabilities.getTransports() == null ? List.of() : remoteCapabilities.getTransports()
        );
        List<String> shared = new ArrayList<>();
        if (capabilities.getTransports() != null) {
            for (String localTransport : capabilities.getTransports()) {
                if (remoteTransports.contains(localTransport)) {
                    shared.add(localTransport.toLowerCase());
                }
            }
        }

        String directEndpoint = asString(asMap(identityDocument.get("service")).get("direct_endpoint"));
        boolean hasDirect = directEndpoint != null && !directEndpoint.isBlank();
        boolean directAvailable = hasDirect && shared.stream().anyMatch(item -> Set.of("https", "http", "direct").contains(item));
        boolean relayAvailable = !isBlank(relayUrl) && shared.contains("relay");
        Map<String, Object> amqpService = asMap(asMap(identityDocument.get("service")).get("amqp"));
        boolean amqpAvailable = shared.contains("amqp")
            && !isBlank(asString(amqpService.get("broker_url")));
        Map<String, Object> mqttService = asMap(asMap(identityDocument.get("service")).get("mqtt"));
        boolean mqttAvailable = shared.contains("mqtt")
            && !isBlank(asString(mqttService.get("broker_url")))
            && !isBlank(asString(mqttService.get("topic")));

        if (mode == DeliveryMode.DIRECT) {
            return directAvailable
                ? new ChannelChoice("direct", directEndpoint, null, null, null)
                : new ChannelChoice(null, null, null, null, "No compatible direct transport and endpoint available");
        }
        if (mode == DeliveryMode.RELAY) {
            return relayAvailable
                ? new ChannelChoice("relay", null, null, null, null)
                : new ChannelChoice(null, null, null, null, "No compatible relay transport available");
        }
        if (mode == DeliveryMode.AMQP) {
            return amqpAvailable
                ? new ChannelChoice("amqp", null, amqpService, null, null)
                : new ChannelChoice(null, null, null, null, "No compatible AMQP transport available");
        }
        if (mode == DeliveryMode.MQTT) {
            return mqttAvailable
                ? new ChannelChoice("mqtt", null, null, mqttService, null)
                : new ChannelChoice(null, null, null, null, "No compatible MQTT transport available");
        }
        if (directAvailable) {
            return new ChannelChoice("direct", directEndpoint, null, null, null);
        }
        if (relayAvailable) {
            return new ChannelChoice("relay", null, null, null, null);
        }
        if (amqpAvailable) {
            return new ChannelChoice("amqp", null, amqpService, null, null);
        }
        if (mqttAvailable) {
            return new ChannelChoice("mqtt", null, null, mqttService, null);
        }
        if (hasDirect) {
            return new ChannelChoice(null, null, null, null, "No compatible transport implementation available for this recipient");
        }
        if (!amqpService.isEmpty()) {
            return new ChannelChoice(
                null,
                null,
                null,
                null,
                "AMQP transport is advertised but not compatible with sender capabilities"
            );
        }
        if (!mqttService.isEmpty()) {
            return new ChannelChoice(
                null,
                null,
                null,
                null,
                "MQTT transport is advertised but not compatible with sender capabilities"
            );
        }
        return new ChannelChoice(
            null,
            null,
            null,
            null,
            "Recipient identity document is missing direct_endpoint/amqp/mqtt and no relay fallback is compatible"
        );
    }

    private Map<String, String> toPublicKeyMap(List<ResolvedRecipient> targets) {
        Map<String, String> publicKeys = new LinkedHashMap<>();
        for (ResolvedRecipient target : targets) {
            publicKeys.put(target.recipient(), target.publicKey());
        }
        return publicKeys;
    }

    private AcpMessage buildMessage(
        List<String> recipients,
        Map<String, Object> payload,
        Map<String, String> recipientPublicKeys,
        MessageClass messageClass,
        String contextId,
        String operationId,
        int expiresInSeconds,
        String correlationId,
        String inReplyTo
    ) {
        Envelope envelope = Envelope.build(
            getAgentId(),
            recipients,
            messageClass,
            contextId,
            expiresInSeconds,
            operationId,
            correlationId,
            inReplyTo,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        ProtectedPayload protectedPayload = CryptoSupport.encryptForRecipients(payload, envelope, recipientPublicKeys);
        protectedPayload = CryptoSupport.signProtectedPayload(
            envelope,
            protectedPayload,
            identity.getSigningPrivateKey(),
            identity.getSigningKid()
        );
        return new AcpMessage(envelope, protectedPayload, identityDocument);
    }

    private List<DeliveryOutcome> deliverDirect(AcpMessage message, List<ResolvedRecipient> targets) {
        List<DeliveryOutcome> outcomes = new ArrayList<>();
        for (ResolvedRecipient target : targets) {
            if (target.endpoint() == null) {
                outcomes.add(failedOutcome(
                    target.recipient(),
                    FailReason.POLICY_REJECTED.name(),
                    "Missing direct endpoint for direct delivery"
                ));
                continue;
            }
            try {
                TransportClient.TransportResponse response = transport.postJson(target.endpoint(), message.toMap());
                outcomes.add(outcomeFromHttpResponse(target.recipient(), response.statusCode(), response.body()));
            } catch (Exception exc) {
                outcomes.add(failedOutcome(
                    target.recipient(),
                    FailReason.POLICY_REJECTED.name(),
                    "Direct transport failure: " + exc.getMessage()
                ));
            }
        }
        return outcomes;
    }

    @SuppressWarnings("unchecked")
    private List<DeliveryOutcome> deliverViaRelay(AcpMessage message, List<ResolvedRecipient> targets) {
        List<DeliveryOutcome> outcomes = new ArrayList<>();
        try {
            Map<String, Object> relayResponse = transport.sendToRelay(relayUrl, message);
            List<String> delivered = new ArrayList<>();
            Object rawOutcomes = relayResponse.get("outcomes");
            if (rawOutcomes instanceof List<?> list) {
                for (Object item : list) {
                    if (item instanceof Map<?, ?> raw) {
                        DeliveryOutcome outcome = JsonSupport.convert(raw, DeliveryOutcome.class);
                        outcomes.add(outcome);
                        delivered.add(outcome.getRecipient());
                    }
                }
            }
            for (ResolvedRecipient target : targets) {
                if (!delivered.contains(target.recipient())) {
                    outcomes.add(failedOutcome(
                        target.recipient(),
                        FailReason.POLICY_REJECTED.name(),
                        "Relay did not return an outcome for recipient"
                    ));
                }
            }
        } catch (Exception exc) {
            for (ResolvedRecipient target : targets) {
                outcomes.add(failedOutcome(
                    target.recipient(),
                    FailReason.POLICY_REJECTED.name(),
                    "Relay transport failure: " + exc.getMessage()
                ));
            }
        }
        return outcomes;
    }

    private DeliveryOutcome deliverViaAmqp(AcpMessage message, ResolvedRecipient target) {
        DeliveryOutcome outcome = new DeliveryOutcome();
        outcome.setRecipient(target.recipient());
        try {
            AmqpTransportClient client = amqpTransport;
            if (client == null) {
                String brokerUrl = asString(asMap(target.amqpService()).get("broker_url"));
                if (isBlank(brokerUrl)) {
                    throw new IllegalStateException(
                        "AMQP delivery selected but sender is not configured with an AMQP broker"
                    );
                }
                client = new AmqpTransportClient(
                    brokerUrl,
                    asString(asMap(target.amqpService()).get("exchange")),
                    AmqpTransportClient.DEFAULT_EXCHANGE_TYPE,
                    10
                );
            }
            client.publish(message.toMap(), target.recipient(), target.amqpService());
            outcome.setState(DeliveryState.DELIVERED);
            return outcome;
        } catch (Exception exc) {
            outcome.setState(DeliveryState.FAILED);
            outcome.setReasonCode(FailReason.POLICY_REJECTED.name());
            outcome.setDetail("AMQP transport failure: " + exc.getMessage());
            return outcome;
        }
    }

    private DeliveryOutcome deliverViaMqtt(AcpMessage message, ResolvedRecipient target) {
        DeliveryOutcome outcome = new DeliveryOutcome();
        outcome.setRecipient(target.recipient());
        try {
            Map<String, Object> targetMqttService = target.mqttService() == null ? Map.of() : target.mqttService();
            MqttTransportClient client = mqttTransport;
            if (client == null) {
                String brokerUrl = asString(asMap(targetMqttService).get("broker_url"));
                if (isBlank(brokerUrl)) {
                    throw new IllegalStateException(
                        "MQTT delivery selected but sender is not configured with an MQTT broker"
                    );
                }
                client = new MqttTransportClient(
                    brokerUrl,
                    targetMqttService.get("qos") instanceof Number qos ? qos.intValue() : MqttTransportClient.DEFAULT_QOS,
                    MqttTransportClient.DEFAULT_TOPIC_PREFIX,
                    10,
                    30
                );
            }
            client.publish(message.toMap(), target.recipient(), targetMqttService);
            outcome.setState(DeliveryState.DELIVERED);
            return outcome;
        } catch (Exception exc) {
            outcome.setState(DeliveryState.FAILED);
            outcome.setReasonCode(FailReason.POLICY_REJECTED.name());
            outcome.setDetail("MQTT transport failure: " + exc.getMessage());
            return outcome;
        }
    }

    private DeliveryOutcome outcomeFromHttpResponse(String recipient, int statusCode, Map<String, Object> body) {
        MessageClass responseClass = null;
        Map<String, Object> responseMessage = null;
        String reasonCode = null;
        String detail = null;

        if (body != null) {
            Object rawResponseMessage = body.get("response_message");
            if (rawResponseMessage instanceof Map<?, ?>) {
                responseMessage = asMap(rawResponseMessage);
                String responseClassRaw = asString(asMap(responseMessage.get("envelope")).get("message_class"));
                if (responseClassRaw != null) {
                    try {
                        responseClass = MessageClass.valueOf(responseClassRaw);
                    } catch (IllegalArgumentException ignored) {
                        responseClass = null;
                    }
                }
            }
            reasonCode = asString(body.get("reason_code"));
            detail = asString(body.get("detail"));
        }
        if (detail == null && statusCode >= 400) {
            detail = "Recipient HTTP " + statusCode;
        }

        DeliveryOutcome outcome = new DeliveryOutcome();
        outcome.setRecipient(recipient);
        outcome.setStatusCode(statusCode);
        outcome.setResponseClass(responseClass);
        outcome.setReasonCode(reasonCode);
        outcome.setDetail(detail);
        outcome.setResponseMessage(responseMessage);
        outcome.setState(deliveryStateFromResponse(statusCode, responseClass, reasonCode));
        return outcome;
    }

    private DeliveryState deliveryStateFromResponse(int statusCode, MessageClass responseClass, String reasonCode) {
        if (statusCode >= 200 && statusCode < 300) {
            if (responseClass == MessageClass.FAIL) {
                if (FailReason.EXPIRED_MESSAGE.name().equals(reasonCode)) {
                    return DeliveryState.EXPIRED;
                }
                if (FailReason.POLICY_REJECTED.name().equals(reasonCode)) {
                    return DeliveryState.DECLINED;
                }
                return DeliveryState.FAILED;
            }
            if (responseClass == MessageClass.ACK || responseClass == MessageClass.CAPABILITIES) {
                return DeliveryState.ACKNOWLEDGED;
            }
            return DeliveryState.DELIVERED;
        }
        if (statusCode == 410) {
            return DeliveryState.EXPIRED;
        }
        if (Set.of(401, 403, 409, 422).contains(statusCode)) {
            return DeliveryState.DECLINED;
        }
        return DeliveryState.FAILED;
    }

    private void syncDeliveryStates(String operationId, List<DeliveryOutcome> outcomes) {
        Map<String, String> states = new LinkedHashMap<>();
        for (DeliveryOutcome outcome : outcomes) {
            states.put(outcome.getRecipient(), outcome.getState().name());
        }
        deliveryStates.put(operationId, states);
    }

    private Map<String, Object> resolveSenderIdentityDocument(Map<String, Object> rawMessage, String senderId) {
        Map<String, Object> embedded = asMap(rawMessage.get("sender_identity_document"));
        if (!embedded.isEmpty()
            && senderId.equals(asString(embedded.get("agent_id")))
            && AgentIdentity.verifyIdentityDocument(embedded)) {
            return embedded;
        }
        return discovery.resolve(senderId);
    }

    private void validateEnvelopeForInbound(Envelope envelope) {
        if (!AcpConstants.ACP_VERSION.equals(envelope.getAcpVersion())) {
            throw new ProcessingException(FailReason.UNSUPPORTED_VERSION, "Unsupported ACP version: " + envelope.getAcpVersion());
        }
        if (!AcpConstants.DEFAULT_CRYPTO_SUITE.equals(envelope.getCryptoSuite())) {
            throw new ProcessingException(
                FailReason.UNSUPPORTED_CRYPTO_SUITE,
                "Unsupported crypto suite: " + envelope.getCryptoSuite()
            );
        }
        if (envelope.isExpired()) {
            throw new ProcessingException(FailReason.EXPIRED_MESSAGE, "Message is expired");
        }
    }

    private AcpMessage createResponseMessage(
        Map<String, Object> senderIdentityDocument,
        Envelope requestEnvelope,
        MessageClass responseClass,
        Map<String, Object> responsePayload
    ) {
        String senderId = requestEnvelope.getSender();
        String senderEncryptionPublicKey = asString(
            asMap(asMap(senderIdentityDocument.get("keys")).get("encryption")).get("public_key")
        );
        if (senderEncryptionPublicKey == null) {
            throw new ProcessingException(
                FailReason.POLICY_REJECTED,
                "Sender identity document missing encryption key"
            );
        }
        return buildMessage(
            List.of(senderId),
            responsePayload,
            Map.of(senderId, senderEncryptionPublicKey),
            responseClass,
            requestEnvelope.getContextId(),
            requestEnvelope.getOperationId(),
            300,
            requestEnvelope.getCorrelationId() != null
                ? requestEnvelope.getCorrelationId()
                : requestEnvelope.getOperationId(),
            requestEnvelope.getMessageId()
        );
    }

    private static DeliveryOutcome failedOutcome(String recipient, String reasonCode, String detail) {
        DeliveryOutcome outcome = new DeliveryOutcome();
        outcome.setRecipient(recipient);
        outcome.setState(DeliveryState.FAILED);
        outcome.setReasonCode(reasonCode);
        outcome.setDetail(detail);
        return outcome;
    }

    private static Map<String, Object> buildAckPayload(String receivedMessageId, String status) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("status", status);
        value.put("received_message_id", receivedMessageId);
        return value;
    }

    private static Map<String, Object> buildFailPayload(String reasonCode, String detail, boolean retriable) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("reason_code", reasonCode);
        value.put("detail", detail);
        value.put("retriable", retriable);
        return value;
    }

    private static FailReason reasonForCapabilityMismatch(String reason) {
        String lower = reason == null ? "" : reason.toLowerCase();
        if (lower.contains("protocol")) {
            return FailReason.UNSUPPORTED_VERSION;
        }
        if (lower.contains("crypto")) {
            return FailReason.UNSUPPORTED_CRYPTO_SUITE;
        }
        if (lower.contains("profile")) {
            return FailReason.UNSUPPORTED_PROFILE;
        }
        return FailReason.POLICY_REJECTED;
    }

    private static Map<String, Object> buildLocalAmqpService(String agentId, AcpAgentOptions options) {
        if (options.getAmqpBrokerUrl() == null || options.getAmqpBrokerUrl().isBlank()) {
            return null;
        }
        return AmqpTransportClient.buildServiceHint(
            agentId,
            options.getAmqpBrokerUrl(),
            options.getAmqpExchange()
        );
    }

    private static Map<String, Object> buildLocalMqttService(String agentId, AcpAgentOptions options) {
        if (options.getMqttBrokerUrl() == null || options.getMqttBrokerUrl().isBlank()) {
            return null;
        }
        return MqttTransportClient.buildServiceHint(
            agentId,
            options.getMqttBrokerUrl(),
            null,
            options.getMqttQos(),
            options.getMqttTopicPrefix()
        );
    }

    private static void applyHttpSecurityProfile(Map<String, Object> identityDocument, boolean mtlsEnabled) {
        if (!mtlsEnabled) {
            return;
        }
        Map<String, Object> existingService = asMap(identityDocument.get("service"));
        Map<String, Object> service = new HashMap<>(existingService);
        String directEndpoint = asString(service.get("direct_endpoint"));
        List<String> relayHints = asStringList(service.get("relay_hints"));
        if (!isBlank(directEndpoint)) {
            service.put(
                "http",
                Map.of(
                    "endpoint",
                    directEndpoint,
                    "security_profile",
                    "mtls"
                )
            );
        }
        if (!relayHints.isEmpty()) {
            service.put(
                "relay",
                Map.of(
                    "endpoint",
                    relayHints.get(0),
                    "security_profile",
                    "mtls"
                )
            );
        }
        identityDocument.put("service", service);
    }

    private static KeyProvider resolveKeyProvider(AcpAgentOptions options, Path storageDir) {
        if (options.getKeyProviderInstance() != null) {
            return options.getKeyProviderInstance();
        }
        String providerName = normalizeKeyProviderName(options.getKeyProvider());
        if ("local".equals(providerName)) {
            return new LocalKeyProvider(
                storageDir,
                options.getCertFile(),
                options.getKeyFile(),
                options.getCaFile()
            );
        }
        if ("vault".equals(providerName)) {
            String vaultUrl = options.getVaultUrl();
            String vaultPath = options.getVaultPath();
            if (isBlank(vaultUrl)) {
                throw new IllegalStateException("vaultUrl is required when keyProvider=vault");
            }
            if (isBlank(vaultPath)) {
                throw new IllegalStateException("vaultPath is required when keyProvider=vault");
            }
            return new VaultKeyProvider(
                vaultUrl,
                vaultPath,
                options.getVaultTokenEnv(),
                options.getVaultToken(),
                options.getHttpTimeoutSeconds(),
                options.getCaFile(),
                options.isAllowInsecureTls(),
                options.isAllowInsecureHttp()
            );
        }
        throw new IllegalStateException("Unsupported keyProvider: " + options.getKeyProvider());
    }

    private static String normalizeKeyProviderName(String value) {
        if (isBlank(value)) {
            return "local";
        }
        return value.trim().toLowerCase();
    }

    private static boolean isExternalKeyProvider(KeyProvider keyProvider) {
        return !(keyProvider instanceof LocalKeyProvider);
    }

    private static AgentIdentity identityFromProvider(String agentId, IdentityKeyMaterial keys) {
        List<String> missing = new ArrayList<>();
        if (isBlank(keys.getSigningPublicKey())) {
            missing.add("signing_public_key");
        }
        if (isBlank(keys.getEncryptionPublicKey())) {
            missing.add("encryption_public_key");
        }
        if (isBlank(keys.getSigningKid())) {
            missing.add("signing_kid");
        }
        if (isBlank(keys.getEncryptionKid())) {
            missing.add("encryption_kid");
        }
        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                "External key provider requires identity public metadata for first-time bootstrap: "
                    + String.join(", ", missing)
            );
        }
        AgentIdentity identity = new AgentIdentity();
        identity.setAgentId(agentId);
        identity.setSigningPrivateKey(keys.getSigningPrivateKey());
        identity.setSigningPublicKey(keys.getSigningPublicKey());
        identity.setEncryptionPrivateKey(keys.getEncryptionPrivateKey());
        identity.setEncryptionPublicKey(keys.getEncryptionPublicKey());
        identity.setSigningKid(keys.getSigningKid());
        identity.setEncryptionKid(keys.getEncryptionKid());
        return identity;
    }

    private static AgentIdentity applyProviderKeys(AgentIdentity identity, IdentityKeyMaterial keys) {
        if (!isBlank(keys.getSigningPublicKey()) && !keys.getSigningPublicKey().equals(identity.getSigningPublicKey())) {
            throw new IllegalStateException("Key provider signing_public_key does not match local identity metadata");
        }
        if (!isBlank(keys.getEncryptionPublicKey())
            && !keys.getEncryptionPublicKey().equals(identity.getEncryptionPublicKey())) {
            throw new IllegalStateException("Key provider encryption_public_key does not match local identity metadata");
        }
        if (!isBlank(keys.getSigningKid()) && !keys.getSigningKid().equals(identity.getSigningKid())) {
            throw new IllegalStateException("Key provider signing_kid does not match local identity metadata");
        }
        if (!isBlank(keys.getEncryptionKid()) && !keys.getEncryptionKid().equals(identity.getEncryptionKid())) {
            throw new IllegalStateException("Key provider encryption_kid does not match local identity metadata");
        }
        AgentIdentity resolved = new AgentIdentity();
        resolved.setAgentId(identity.getAgentId());
        resolved.setSigningPrivateKey(keys.getSigningPrivateKey());
        resolved.setSigningPublicKey(identity.getSigningPublicKey());
        resolved.setEncryptionPrivateKey(keys.getEncryptionPrivateKey());
        resolved.setEncryptionPublicKey(identity.getEncryptionPublicKey());
        resolved.setSigningKid(identity.getSigningKid());
        resolved.setEncryptionKid(identity.getEncryptionKid());
        return resolved;
    }

    private static String baseUrlFromEndpoint(String endpoint) {
        if (isBlank(endpoint)) {
            return null;
        }
        try {
            URI uri = URI.create(endpoint);
            if (isBlank(uri.getScheme()) || isBlank(uri.getHost())) {
                return null;
            }
            return uri.getScheme() + "://" + uri.getAuthority();
        } catch (Exception exc) {
            return null;
        }
    }

    private static String normalizedBaseUrl(String value) {
        if (isBlank(value)) {
            return value;
        }
        return value.replaceAll("/+$", "");
    }

    private static String inferWellKnownSecurityProfile(Map<String, Object> transports) {
        for (String transport : List.of("http", "relay")) {
            String profile = asString(asMap(transports.get(transport)).get("security_profile"));
            if (!isBlank(profile)) {
                return profile;
            }
        }
        String httpEndpoint = asString(asMap(transports.get("http")).get("endpoint"));
        if (!isBlank(httpEndpoint)) {
            if (httpEndpoint.startsWith("https://")) {
                return "https";
            }
            if (httpEndpoint.startsWith("http://")) {
                return "http";
            }
        }
        return "https";
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (!isBlank(value)) {
                return value.trim();
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return Map.of();
    }

    private static List<String> asStringList(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        List<String> result = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof String str) {
                result.add(str);
            }
        }
        return result;
    }

    private static String asString(Object value) {
        return value instanceof String str ? str : null;
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private record ResolvedRecipient(
        String recipient,
        String publicKey,
        Map<String, Object> identityDocument,
        String channel,
        String endpoint,
        Map<String, Object> amqpService,
        Map<String, Object> mqttService
    ) {
    }

    private record ResolvedRecipients(List<ResolvedRecipient> deliverable, List<DeliveryOutcome> preflightOutcomes) {
    }

    private record ChannelChoice(
        String channel,
        String endpoint,
        Map<String, Object> amqpService,
        Map<String, Object> mqttService,
        String detail
    ) {
    }

    public record CapabilityRequestResult(SendResult result, Map<String, Object> capabilities) {
    }
}
