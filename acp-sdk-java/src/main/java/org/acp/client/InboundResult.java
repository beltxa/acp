package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

public class InboundResult {
    private DeliveryState state;
    @JsonProperty("reason_code")
    private String reasonCode;
    private String detail;
    @JsonProperty("decrypted_payload")
    private Map<String, Object> decryptedPayload;
    @JsonProperty("response_message")
    private Map<String, Object> responseMessage;

    public InboundResult() {
    }

    public DeliveryState getState() {
        return state;
    }

    public void setState(DeliveryState state) {
        this.state = state;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public void setReasonCode(String reasonCode) {
        this.reasonCode = reasonCode;
    }

    public String getDetail() {
        return detail;
    }

    public void setDetail(String detail) {
        this.detail = detail;
    }

    public Map<String, Object> getDecryptedPayload() {
        return decryptedPayload;
    }

    public void setDecryptedPayload(Map<String, Object> decryptedPayload) {
        this.decryptedPayload = decryptedPayload;
    }

    public Map<String, Object> getResponseMessage() {
        return responseMessage;
    }

    public void setResponseMessage(Map<String, Object> responseMessage) {
        this.responseMessage = responseMessage;
    }
}
