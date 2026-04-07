/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

public class TransportConfig {
    private String protocol;
    private String endpoint;
    private AuthConfig auth;

    public TransportConfig() {
    }

    public TransportConfig(String protocol, String endpoint, AuthConfig auth) {
        this.protocol = protocol;
        this.endpoint = endpoint;
        this.auth = auth;
    }

    public String getProtocol() {
        return protocol;
    }

    public TransportConfig setProtocol(String protocol) {
        this.protocol = protocol;
        return this;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public TransportConfig setEndpoint(String endpoint) {
        this.endpoint = endpoint;
        return this;
    }

    public AuthConfig getAuth() {
        return auth;
    }

    public TransportConfig setAuth(AuthConfig auth) {
        this.auth = auth;
        return this;
    }
}
