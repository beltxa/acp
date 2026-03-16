package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

public class AcpMessage {
    private Envelope envelope;
    @JsonProperty("protected")
    private ProtectedPayload protectedPayload;
    @JsonProperty("sender_identity_document")
    private Map<String, Object> senderIdentityDocument;

    public AcpMessage() {
    }

    public AcpMessage(Envelope envelope, ProtectedPayload protectedPayload, Map<String, Object> senderIdentityDocument) {
        this.envelope = envelope;
        this.protectedPayload = protectedPayload;
        this.senderIdentityDocument = senderIdentityDocument;
    }

    public Map<String, Object> toMap() {
        return JsonSupport.toMap(this);
    }

    public String toJson() {
        return JsonSupport.toJson(this);
    }

    public static AcpMessage fromJson(String value) {
        return JsonSupport.fromJson(value, AcpMessage.class);
    }

    public static AcpMessage fromMap(Map<String, Object> value) {
        return JsonSupport.convert(value, AcpMessage.class);
    }

    public Envelope getEnvelope() {
        return envelope;
    }

    public void setEnvelope(Envelope envelope) {
        this.envelope = envelope;
    }

    public ProtectedPayload getProtectedPayload() {
        return protectedPayload;
    }

    public void setProtectedPayload(ProtectedPayload protectedPayload) {
        this.protectedPayload = protectedPayload;
    }

    public Map<String, Object> getSenderIdentityDocument() {
        return senderIdentityDocument;
    }

    public void setSenderIdentityDocument(Map<String, Object> senderIdentityDocument) {
        this.senderIdentityDocument = senderIdentityDocument;
    }
}
