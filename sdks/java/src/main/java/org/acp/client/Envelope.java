/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class Envelope {
    @JsonProperty("acp_version")
    private String acpVersion;
    @JsonProperty("message_class")
    private MessageClass messageClass;
    @JsonProperty("message_id")
    private String messageId;
    @JsonProperty("operation_id")
    private String operationId;
    private String timestamp;
    @JsonProperty("expires_at")
    private String expiresAt;
    private String sender;
    private List<String> recipients;
    @JsonProperty("context_id")
    private String contextId;
    @JsonProperty("crypto_suite")
    private String cryptoSuite;
    @JsonProperty("correlation_id")
    private String correlationId;
    @JsonProperty("in_reply_to")
    private String inReplyTo;

    public Envelope() {
    }

    public static Envelope build(
        String sender,
        List<String> recipients,
        MessageClass messageClass,
        String contextId,
        int expiresInSeconds,
        String operationId,
        String correlationId,
        String inReplyTo,
        String cryptoSuite
    ) {
        Instant now = Instant.now();
        Envelope envelope = new Envelope();
        envelope.acpVersion = AcpConstants.ACP_VERSION;
        envelope.messageClass = messageClass;
        envelope.messageId = UUID.randomUUID().toString();
        envelope.operationId = operationId == null ? UUID.randomUUID().toString() : operationId;
        envelope.timestamp = now.toString();
        envelope.expiresAt = now.plusSeconds(expiresInSeconds).toString();
        envelope.sender = sender;
        envelope.recipients = new ArrayList<>(recipients);
        envelope.contextId = contextId;
        envelope.cryptoSuite = cryptoSuite == null ? AcpConstants.DEFAULT_CRYPTO_SUITE : cryptoSuite;
        envelope.correlationId = correlationId;
        envelope.inReplyTo = inReplyTo;
        envelope.validate();
        return envelope;
    }

    public void validate() {
        if (sender == null || sender.isBlank()) {
            throw new IllegalArgumentException("Envelope sender is required");
        }
        if (recipients == null || recipients.isEmpty()) {
            throw new IllegalArgumentException("Envelope recipients must not be empty");
        }
        if (!Instant.parse(expiresAt).isAfter(Instant.parse(timestamp))) {
            throw new IllegalArgumentException("Envelope expires_at must be after timestamp");
        }
    }

    @JsonIgnore
    public boolean isExpired() {
        return !Instant.parse(expiresAt).isAfter(Instant.now());
    }

    public Map<String, Object> toMap() {
        validate();
        return JsonSupport.toMap(this);
    }

    public String getAcpVersion() {
        return acpVersion;
    }

    public void setAcpVersion(String acpVersion) {
        this.acpVersion = acpVersion;
    }

    public MessageClass getMessageClass() {
        return messageClass;
    }

    public void setMessageClass(MessageClass messageClass) {
        this.messageClass = messageClass;
    }

    public String getMessageId() {
        return messageId;
    }

    public void setMessageId(String messageId) {
        this.messageId = messageId;
    }

    public String getOperationId() {
        return operationId;
    }

    public void setOperationId(String operationId) {
        this.operationId = operationId;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(String timestamp) {
        this.timestamp = timestamp;
    }

    public String getExpiresAt() {
        return expiresAt;
    }

    public void setExpiresAt(String expiresAt) {
        this.expiresAt = expiresAt;
    }

    public String getSender() {
        return sender;
    }

    public void setSender(String sender) {
        this.sender = sender;
    }

    public List<String> getRecipients() {
        return recipients;
    }

    public void setRecipients(List<String> recipients) {
        this.recipients = recipients;
    }

    public String getContextId() {
        return contextId;
    }

    public void setContextId(String contextId) {
        this.contextId = contextId;
    }

    public String getCryptoSuite() {
        return cryptoSuite;
    }

    public void setCryptoSuite(String cryptoSuite) {
        this.cryptoSuite = cryptoSuite;
    }

    public String getCorrelationId() {
        return correlationId;
    }

    public void setCorrelationId(String correlationId) {
        this.correlationId = correlationId;
    }

    public String getInReplyTo() {
        return inReplyTo;
    }

    public void setInReplyTo(String inReplyTo) {
        this.inReplyTo = inReplyTo;
    }
}
