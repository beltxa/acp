/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;
import java.util.Set;

public class TransportClient {
    private static final Set<String> HTTP_AUTH_TYPES = Set.of("none", "bearer", "basic", "mtls", "custom");

    private final HttpClient httpClient;
    private final int timeoutSeconds;
    private final boolean allowInsecureHttp;
    private final boolean allowInsecureTls;
    private final boolean mtlsEnabled;
    private final String caFile;
    private final String certFile;
    private final String keyFile;
    private final AuthConfig defaultAuth;

    public TransportClient(
        int timeoutSeconds,
        boolean allowInsecureHttp,
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile
    ) {
        this(
            timeoutSeconds,
            allowInsecureHttp,
            allowInsecureTls,
            caFile,
            mtlsEnabled,
            certFile,
            keyFile,
            null
        );
    }

    public TransportClient(
        int timeoutSeconds,
        boolean allowInsecureHttp,
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile,
        AuthConfig auth
    ) {
        this.timeoutSeconds = timeoutSeconds <= 0 ? 10 : timeoutSeconds;
        this.allowInsecureHttp = allowInsecureHttp;
        this.allowInsecureTls = allowInsecureTls;
        this.mtlsEnabled = mtlsEnabled;
        this.caFile = caFile;
        this.certFile = certFile;
        this.keyFile = keyFile;
        this.defaultAuth = TransportAuth.normalizeAuthConfig(auth);
        this.httpClient = HttpSecurity.buildHttpClient(
            this.timeoutSeconds,
            allowInsecureTls,
            caFile,
            mtlsEnabled,
            certFile,
            keyFile
        );
    }

    public TransportResponse postJson(String url, Map<String, Object> body) {
        return postJsonWithConfig(url, body, null);
    }

    public TransportResponse postJsonWithConfig(String url, Map<String, Object> body, TransportConfig config) {
        try {
            AuthConfig auth = resolveAuth(config);
            TransportAuth.assertAllowedAuthTypes(auth, HTTP_AUTH_TYPES, "HTTP/relay transport");
            boolean useMtls = mtlsEnabled || (auth != null && "mtls".equals(auth.getType()));
            URI uri = HttpSecurity.validateHttpUrl(url, allowInsecureHttp, useMtls, "HTTP transport request");
            HttpClient activeClient = resolveHttpClientForAuth(auth);

            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder(uri)
                .header("Content-Type", "application/json")
                .timeout(java.time.Duration.ofSeconds(timeoutSeconds))
                .POST(HttpRequest.BodyPublishers.ofString(JsonSupport.toJson(body)));
            for (Map.Entry<String, String> header : TransportAuth.httpAuthHeaders(auth).entrySet()) {
                requestBuilder.header(header.getKey(), header.getValue());
            }
            HttpResponse<String> response = activeClient.send(
                requestBuilder.build(),
                HttpResponse.BodyHandlers.ofString()
            );
            Map<String, Object> parsed = null;
            String rawBody = response.body() == null ? "" : response.body();
            if (!rawBody.isBlank()) {
                try {
                    parsed = JsonSupport.mapFromJson(rawBody);
                } catch (Exception ignored) {
                    parsed = null;
                }
            }
            return new TransportResponse(response.statusCode(), parsed, rawBody);
        } catch (Exception exc) {
            throw new IllegalStateException("HTTP POST failed for " + url + ": " + exc.getMessage(), exc);
        }
    }

    public Map<String, Object> sendToRelay(String relayUrl, AcpMessage message) {
        return sendToRelayWithConfig(relayUrl, message, null);
    }

    public Map<String, Object> sendToRelayWithConfig(String relayUrl, AcpMessage message, TransportConfig config) {
        String url = relayUrl.endsWith("/") ? relayUrl + "messages" : relayUrl + "/messages";
        TransportResponse response = postJsonWithConfig(url, message.toMap(), config);
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "Relay returned HTTP " + response.statusCode() + " for message " + message.getEnvelope().getMessageId()
            );
        }
        if (response.body() == null) {
            throw new IllegalStateException("Relay returned non-JSON response");
        }
        return response.body();
    }

    private AuthConfig resolveAuth(TransportConfig config) {
        if (config != null && config.getAuth() != null) {
            return TransportAuth.normalizeAuthConfig(config.getAuth());
        }
        return defaultAuth;
    }

    private HttpClient resolveHttpClientForAuth(AuthConfig auth) {
        if (auth == null || !"mtls".equals(auth.getType())) {
            return httpClient;
        }
        String certPath = TransportAuth.requireParameter(auth, "cert_path", "mTLS auth");
        String keyPath = TransportAuth.requireParameter(auth, "key_path", "mTLS auth");
        String caPath = TransportAuth.optionalParameter(auth, "ca_path");
        return HttpSecurity.buildHttpClient(
            timeoutSeconds,
            allowInsecureTls,
            caPath == null ? caFile : caPath,
            true,
            certPath,
            keyPath
        );
    }

    public record TransportResponse(int statusCode, Map<String, Object> body, String rawBody) {
    }
}
