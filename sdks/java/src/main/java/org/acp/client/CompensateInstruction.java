package org.acp.client;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class CompensateInstruction {
    private String operationId;
    private String reason;
    private List<Map<String, Object>> actions = new ArrayList<>();

    public CompensateInstruction() {
    }

    public CompensateInstruction(String operationId, String reason, List<Map<String, Object>> actions) {
        this.operationId = operationId;
        this.reason = reason;
        if (actions != null) {
            this.actions = actions;
        }
    }

    public Map<String, Object> toMap() {
        return Map.of(
            "operation_id", operationId,
            "reason", reason,
            "actions", actions
        );
    }

    public String getOperationId() {
        return operationId;
    }

    public void setOperationId(String operationId) {
        this.operationId = operationId;
    }

    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public List<Map<String, Object>> getActions() {
        return actions;
    }

    public void setActions(List<Map<String, Object>> actions) {
        this.actions = actions;
    }
}
