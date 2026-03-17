/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

public class DeliveryOutcome {
    private String recipient;
    private DeliveryState state;
    @JsonProperty("status_code")
    private Integer statusCode;
    @JsonProperty("response_class")
    private MessageClass responseClass;
    @JsonProperty("reason_code")
    private String reasonCode;
    private String detail;
    @JsonProperty("response_message")
    private Map<String, Object> responseMessage;

    public DeliveryOutcome() {
    }

    public static DeliveryOutcome fromMap(Map<String, Object> raw) {
        return JsonSupport.convert(raw, DeliveryOutcome.class);
    }

    public Map<String, Object> toMap() {
        return JsonSupport.toMap(this);
    }

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public DeliveryState getState() {
        return state;
    }

    public void setState(DeliveryState state) {
        this.state = state;
    }

    public Integer getStatusCode() {
        return statusCode;
    }

    public void setStatusCode(Integer statusCode) {
        this.statusCode = statusCode;
    }

    public MessageClass getResponseClass() {
        return responseClass;
    }

    public void setResponseClass(MessageClass responseClass) {
        this.responseClass = responseClass;
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

    public Map<String, Object> getResponseMessage() {
        return responseMessage;
    }

    public void setResponseMessage(Map<String, Object> responseMessage) {
        this.responseMessage = responseMessage;
    }
}
