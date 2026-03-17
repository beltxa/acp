/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

public final class IdentityKeyMaterial {
    private final String signingPrivateKey;
    private final String encryptionPrivateKey;
    private final String signingPublicKey;
    private final String encryptionPublicKey;
    private final String signingKid;
    private final String encryptionKid;

    public IdentityKeyMaterial(
        String signingPrivateKey,
        String encryptionPrivateKey,
        String signingPublicKey,
        String encryptionPublicKey,
        String signingKid,
        String encryptionKid
    ) {
        this.signingPrivateKey = requireValue(signingPrivateKey, "signingPrivateKey");
        this.encryptionPrivateKey = requireValue(encryptionPrivateKey, "encryptionPrivateKey");
        this.signingPublicKey = normalizeOptional(signingPublicKey);
        this.encryptionPublicKey = normalizeOptional(encryptionPublicKey);
        this.signingKid = normalizeOptional(signingKid);
        this.encryptionKid = normalizeOptional(encryptionKid);
    }

    public String getSigningPrivateKey() {
        return signingPrivateKey;
    }

    public String getEncryptionPrivateKey() {
        return encryptionPrivateKey;
    }

    public String getSigningPublicKey() {
        return signingPublicKey;
    }

    public String getEncryptionPublicKey() {
        return encryptionPublicKey;
    }

    public String getSigningKid() {
        return signingKid;
    }

    public String getEncryptionKid() {
        return encryptionKid;
    }

    private static String requireValue(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + " must be provided");
        }
        return value.trim();
    }

    private static String normalizeOptional(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
