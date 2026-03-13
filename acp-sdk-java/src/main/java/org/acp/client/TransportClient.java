package org.acp.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

public class TransportClient {
    private final HttpClient httpClient;
    private final int timeoutSeconds;

    public TransportClient(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds <= 0 ? 10 : timeoutSeconds;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(this.timeoutSeconds))
            .build();
    }

    public TransportResponse postJson(String url, Map<String, Object> body) {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(timeoutSeconds))
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
