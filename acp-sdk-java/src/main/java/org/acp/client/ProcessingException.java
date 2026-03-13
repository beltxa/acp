package org.acp.client;

public class ProcessingException extends RuntimeException {
    private final FailReason reasonCode;

    public ProcessingException(FailReason reasonCode, String detail) {
        super(detail);
        this.reasonCode = reasonCode;
    }

    public FailReason getReasonCode() {
        return reasonCode;
    }
}
