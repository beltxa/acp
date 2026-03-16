package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class SendResult {
    @JsonProperty("operation_id")
    private String operationId;
    @JsonProperty("message_id")
    private String messageId;
    @JsonProperty("message_ids")
    private List<String> messageIds = new ArrayList<>();
    private List<DeliveryOutcome> outcomes = new ArrayList<>();

    public SendResult() {
    }

    public Map<String, Object> toMap() {
        return JsonSupport.toMap(this);
    }

    public String getOperationId() {
        return operationId;
    }

    public void setOperationId(String operationId) {
        this.operationId = operationId;
    }

    public String getMessageId() {
        return messageId;
    }

    public void setMessageId(String messageId) {
        this.messageId = messageId;
    }

    public List<String> getMessageIds() {
        return messageIds;
    }

    public void setMessageIds(List<String> messageIds) {
        this.messageIds = messageIds;
    }

    public List<DeliveryOutcome> getOutcomes() {
        return outcomes;
    }

    public void setOutcomes(List<DeliveryOutcome> outcomes) {
        this.outcomes = outcomes;
    }
}
