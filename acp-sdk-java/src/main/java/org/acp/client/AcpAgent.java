package org.acp.client;

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
    private final AgentIdentity identity;
    private final Map<String, Object> identityDocument;
    private final DiscoveryClient discovery;
    private final TransportClient transport;
    private final AmqpTransportClient amqpTransport;
    private final AgentCapabilities capabilities;
    private final Path storageDir;
    private final String trustProfile;
    private final String relayUrl;
    private final DedupStore dedupStore;
    private final DeliveryMode defaultDeliveryMode;
    private final Map<String, Map<String, String>> deliveryStates = new ConcurrentHashMap<>();

    private AcpAgent(
        AgentIdentity identity,
        Map<String, Object> identityDocument,
        DiscoveryClient discovery,
        TransportClient transport,
        AmqpTransportClient amqpTransport,
        AgentCapabilities capabilities,
        Path storageDir,
        String trustProfile,
        String relayUrl,
        DeliveryMode defaultDeliveryMode
    ) {
        this.identity = identity;
        this.identityDocument = identityDocument;
        this.discovery = discovery;
        this.transport = transport;
        this.amqpTransport = amqpTransport;
        this.capabilities = capabilities;
        this.storageDir = storageDir;
        this.trustProfile = trustProfile;
        this.relayUrl = relayUrl;
        this.defaultDeliveryMode = defaultDeliveryMode == null ? DeliveryMode.AUTO : defaultDeliveryMode;
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

        AgentIdentity identity;
        Map<String, Object> identityDocument;
        AgentIdentity.IdentityBundle existing = AgentIdentity.readIdentity(storage, agentId);
        AgentCapabilities capabilities;
        Map<String, Object> localAmqpService = buildLocalAmqpService(agentId, effective);

        if (existing == null) {
            identity = AgentIdentity.create(agentId);
            capabilities = effective.getCapabilities() == null
                ? new AgentCapabilities(agentId)
                : effective.getCapabilities();
            identityDocument = identity.buildIdentityDocument(
                effective.getEndpoint(),
                effective.getRelayHints(),
                effective.getTrustProfile(),
                capabilities.toMap(),
                365,
                localAmqpService
            );
            AgentIdentity.writeIdentity(storage, identity, identityDocument);
        } else {
            identity = existing.identity();
            identityDocument = existing.identityDocument();
            boolean validDocument = AgentIdentity.verifyIdentityDocument(identityDocument);
            capabilities = effective.getCapabilities() != null
                ? effective.getCapabilities()
                : AgentCapabilities.fromMap(asMap(identityDocument.get("capabilities")), agentId);

            boolean shouldRewrite = !validDocument
                || effective.getEndpoint() != null
                || (effective.getRelayHints() != null && !effective.getRelayHints().isEmpty())
                || effective.getCapabilities() != null
                || localAmqpService != null;
            if (shouldRewrite) {
                String existingEndpoint = asString(asMap(identityDocument.get("service")).get("direct_endpoint"));
                List<String> existingHints = asStringList(asMap(identityDocument.get("service")).get("relay_hints"));
                Map<String, Object> existingAmqpService = asMap(asMap(identityDocument.get("service")).get("amqp"));
                identityDocument = identity.buildIdentityDocument(
                    effective.getEndpoint() != null ? effective.getEndpoint() : existingEndpoint,
                    effective.getRelayHints() != null && !effective.getRelayHints().isEmpty()
                        ? effective.getRelayHints()
                        : existingHints,
                    effective.getTrustProfile(),
                    capabilities.toMap(),
                    365,
                    localAmqpService != null ? localAmqpService : existingAmqpService
                );
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
            effective.getHttpTimeoutSeconds()
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

        return new AcpAgent(
            identity,
            identityDocument,
            discovery,
            new TransportClient(effective.getHttpTimeoutSeconds()),
            amqpTransport,
            capabilities,
            storage,
            effective.getTrustProfile(),
            effective.getRelayUrl(),
            effective.getDefaultDeliveryMode()
        );
    }

    public String getAgentId() {
        return identity.getAgentId();
    }

    public Map<String, Object> getIdentityDocument() {
        return identityDocument;
    }

    public void registerIdentityDocument(Map<String, Object> identityDocument) {
        discovery.registerIdentityDocument(identityDocument);
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
                choice.amqpService()
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

        if (mode == DeliveryMode.DIRECT) {
            return directAvailable
                ? new ChannelChoice("direct", directEndpoint, null, null)
                : new ChannelChoice(null, null, null, "No compatible direct transport and endpoint available");
        }
        if (mode == DeliveryMode.RELAY) {
            return relayAvailable
                ? new ChannelChoice("relay", null, null, null)
                : new ChannelChoice(null, null, null, "No compatible relay transport available");
        }
        if (mode == DeliveryMode.AMQP) {
            return amqpAvailable
                ? new ChannelChoice("amqp", null, amqpService, null)
                : new ChannelChoice(null, null, null, "No compatible AMQP transport available");
        }
        if (directAvailable) {
            return new ChannelChoice("direct", directEndpoint, null, null);
        }
        if (relayAvailable) {
            return new ChannelChoice("relay", null, null, null);
        }
        if (amqpAvailable) {
            return new ChannelChoice("amqp", null, amqpService, null);
        }
        if (hasDirect) {
            return new ChannelChoice(null, null, null, "No compatible transport implementation available for this recipient");
        }
        if (!amqpService.isEmpty()) {
            return new ChannelChoice(null, null, null, "AMQP transport is advertised but not compatible with sender capabilities");
        }
        return new ChannelChoice(
            null,
            null,
            null,
            "Recipient identity document is missing direct_endpoint and no relay fallback is compatible"
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

    private DeliveryOutcome outcomeFromHttpResponse(String recipient, int statusCode, Map<String, Object> body) {
        MessageClass responseClass = null;
        Map<String, Object> responseMessage = null;
        String reasonCode = null;
        String detail = null;

        if (body != null) {
            Object rawResponseMessage = body.get("response_message");
            if (rawResponseMessage instanceof Map<?, ?> raw) {
                responseMessage = (Map<String, Object>) raw;
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
        Map<String, Object> amqpService
    ) {
    }

    private record ResolvedRecipients(List<ResolvedRecipient> deliverable, List<DeliveryOutcome> preflightOutcomes) {
    }

    private record ChannelChoice(String channel, String endpoint, Map<String, Object> amqpService, String detail) {
    }

    public record CapabilityRequestResult(SendResult result, Map<String, Object> capabilities) {
    }
}
