/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

public final class TlsMaterial {
    private final String certFile;
    private final String keyFile;
    private final String caFile;

    public TlsMaterial(String certFile, String keyFile, String caFile) {
        this.certFile = normalizeOptional(certFile);
        this.keyFile = normalizeOptional(keyFile);
        this.caFile = normalizeOptional(caFile);
    }

    public String getCertFile() {
        return certFile;
    }

    public String getKeyFile() {
        return keyFile;
    }

    public String getCaFile() {
        return caFile;
    }

    private static String normalizeOptional(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
