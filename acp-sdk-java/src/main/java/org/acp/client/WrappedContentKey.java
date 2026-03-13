package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

public class WrappedContentKey {
    private String recipient;
    @JsonProperty("ephemeral_public_key")
    private String ephemeralPublicKey;
    private String nonce;
    private String ciphertext;

    public WrappedContentKey() {
    }

    public WrappedContentKey(String recipient, String ephemeralPublicKey, String nonce, String ciphertext) {
        this.recipient = recipient;
        this.ephemeralPublicKey = ephemeralPublicKey;
        this.nonce = nonce;
        this.ciphertext = ciphertext;
    }

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getEphemeralPublicKey() {
        return ephemeralPublicKey;
    }

    public void setEphemeralPublicKey(String ephemeralPublicKey) {
        this.ephemeralPublicKey = ephemeralPublicKey;
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
}
