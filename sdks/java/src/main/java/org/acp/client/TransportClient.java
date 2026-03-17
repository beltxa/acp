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

public class TransportClient {
    private final HttpClient httpClient;
    private final int timeoutSeconds;
    private final boolean allowInsecureHttp;
    private final boolean mtlsEnabled;

    public TransportClient(
        int timeoutSeconds,
        boolean allowInsecureHttp,
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile
    ) {
        this.timeoutSeconds = timeoutSeconds <= 0 ? 10 : timeoutSeconds;
        this.allowInsecureHttp = allowInsecureHttp;
        this.mtlsEnabled = mtlsEnabled;
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
        try {
            URI uri = HttpSecurity.validateHttpUrl(url, allowInsecureHttp, mtlsEnabled, "HTTP transport request");
            HttpRequest request = HttpRequest.newBuilder(uri)
                .header("Content-Type", "application/json")
                .timeout(java.time.Duration.ofSeconds(timeoutSeconds))
                .POST(HttpRequest.BodyPublishers.ofString(JsonSupport.toJson(body)))
                .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
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
        String url = relayUrl.endsWith("/") ? relayUrl + "messages" : relayUrl + "/messages";
        TransportResponse response = postJson(url, message.toMap());
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

    public record TransportResponse(int statusCode, Map<String, Object> body, String rawBody) {
    }
}
