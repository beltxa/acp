/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

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
