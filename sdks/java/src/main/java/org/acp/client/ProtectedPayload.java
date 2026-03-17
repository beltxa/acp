/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ProtectedPayload {
    private String nonce;
    private String ciphertext;
    @JsonProperty("wrapped_content_keys")
    private List<WrappedContentKey> wrappedContentKeys = new ArrayList<>();
    @JsonProperty("payload_hash")
    private String payloadHash;
    @JsonProperty("signature_kid")
    private String signatureKid;
    private String signature;

    public ProtectedPayload() {
    }

    public Map<String, Object> toSignableMap() {
        List<Map<String, Object>> keys = new ArrayList<>();
        wrappedContentKeys.stream()
            .sorted(Comparator.comparing(WrappedContentKey::getRecipient))
            .forEach(item -> keys.add(JsonSupport.toMap(item)));
        Map<String, Object> value = new HashMap<>();
        value.put("nonce", nonce);
        value.put("ciphertext", ciphertext);
        value.put("wrapped_content_keys", keys);
        value.put("payload_hash", payloadHash);
        value.put("signature_kid", signatureKid);
        return value;
    }

    public String getNonce() {
        return nonce;
    }

    public void setNonce(String nonce) {
        this.nonce = nonce;
    }

    public String getCiphertext() {
        return ciphertext;
    }

    public void setCiphertext(String ciphertext) {
        this.ciphertext = ciphertext;
    }

    public List<WrappedContentKey> getWrappedContentKeys() {
        return wrappedContentKeys;
    }

    public void setWrappedContentKeys(List<WrappedContentKey> wrappedContentKeys) {
        this.wrappedContentKeys = wrappedContentKeys;
    }

    public String getPayloadHash() {
        return payloadHash;
    }

    public void setPayloadHash(String payloadHash) {
        this.payloadHash = payloadHash;
    }

    public String getSignatureKid() {
        return signatureKid;
    }

    public void setSignatureKid(String signatureKid) {
        this.signatureKid = signatureKid;
    }

    public String getSignature() {
        return signature;
    }

    public void setSignature(String signature) {
        this.signature = signature;
    }
}
