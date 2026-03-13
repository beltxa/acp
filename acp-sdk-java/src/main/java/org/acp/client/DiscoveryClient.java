package org.acp.client;

import com.fasterxml.jackson.core.type.TypeReference;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class DiscoveryClient {
    private final Path cachePath;
    private final String defaultScheme;
    private final List<String> relayHints;
    private final List<String> enterpriseDirectoryHints;
    private final int timeoutSeconds;
    private final HttpClient httpClient;
    private final Map<String, CachedDocument> cache = new ConcurrentHashMap<>();
    private final Map<String, Map<String, Object>> registry = new ConcurrentHashMap<>();

    public DiscoveryClient(
        Path cachePath,
        String defaultScheme,
        List<String> relayHints,
        List<String> enterpriseDirectoryHints,
        int timeoutSeconds
    ) {
        this.cachePath = cachePath;
        this.defaultScheme = defaultScheme == null ? "https" : defaultScheme;
        this.relayHints = relayHints == null ? List.of() : List.copyOf(relayHints);
        this.enterpriseDirectoryHints = enterpriseDirectoryHints == null ? List.of() : List.copyOf(enterpriseDirectoryHints);
        this.timeoutSeconds = timeoutSeconds <= 0 ? 5 : timeoutSeconds;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(this.timeoutSeconds))
            .build();
        loadCache();
    }

    public void seed(Map<String, Object> identityDocument) {
        String agentId = asString(identityDocument.get("agent_id"));
        if (agentId == null || agentId.isBlank()) {
            return;
        }
        cache.put(agentId, new CachedDocument(identityDocument, Instant.now().toString()));
        persistCache();
    }

    public void registerIdentityDocument(Map<String, Object> identityDocument) {
        String agentId = asString(identityDocument.get("agent_id"));
        if (agentId == null || agentId.isBlank()) {
            throw new IllegalArgumentException("Identity document missing agent_id");
        }
        registry.put(agentId, identityDocument);
        cache.put(agentId, new CachedDocument(identityDocument, Instant.now().toString()));
        persistCache();
    }

    public Map<String, Object> resolve(String agentId) {
        if (registry.containsKey(agentId)) {
            return registry.get(agentId);
        }
        Map<String, Object> cached = tryCache(agentId);
        if (cached != null) {
            return cached;
        }
        Map<String, Object> wellKnown = tryWellKnown(agentId);
        if (wellKnown != null) {
            cacheIdentity(agentId, wellKnown);
            return wellKnown;
        }
        Map<String, Object> relay = tryHintLookups(relayHints, agentId);
        if (relay != null) {
            cacheIdentity(agentId, relay);
            return relay;
        }
        Map<String, Object> enterprise = tryHintLookups(enterpriseDirectoryHints, agentId);
        if (enterprise != null) {
            cacheIdentity(agentId, enterprise);
            return enterprise;
        }
        throw new IllegalStateException("Unable to resolve identity document for " + agentId);
    }

    private Map<String, Object> tryCache(String agentId) {
        CachedDocument cached = cache.get(agentId);
        if (cached == null) {
            return null;
        }
        if (cacheValid(cached.identityDocument())) {
            return cached.identityDocument();
        }
        cache.remove(agentId);
        persistCache();
        return null;
    }

    private Map<String, Object> tryWellKnown(String agentId) {
        AgentIdentity.AgentIdParts parts;
        try {
            parts = AgentIdentity.parseAgentId(agentId);
        } catch (Exception exc) {
            return null;
        }
        if (parts.domain() == null || parts.domain().isBlank()) {
            return null;
        }
        String url = defaultScheme + "://" + parts.domain() + "/.well-known/acp/agents/" + parts.name();
        return fetchIdentityDocument(url, null);
    }

    private Map<String, Object> tryHintLookups(List<String> hints, String agentId) {
        for (String hint : hints) {
            String base = hint.endsWith("/") ? hint.substring(0, hint.length() - 1) : hint;
            Map<String, Object> value = fetchIdentityDocument(base + "/discover", Map.of("agent_id", agentId));
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> fetchIdentityDocument(String url, Map<String, String> queryParams) {
        try {
            URI uri = URI.create(queryParams == null ? url : withQuery(url, queryParams));
            HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                return null;
            }
            Map<String, Object> body = JsonSupport.mapFromJson(response.body());
            Object identityDocument = body.get("identity_document");
            if (identityDocument instanceof Map<?, ?> raw) {
                Map<String, Object> asMap = (Map<String, Object>) raw;
                return validateIdentityDocument(asMap) ? asMap : null;
            }
            return validateIdentityDocument(body) ? body : null;
        } catch (Exception exc) {
            return null;
        }
    }

    private boolean validateIdentityDocument(Map<String, Object> identityDocument) {
        return AgentIdentity.verifyIdentityDocument(identityDocument) && cacheValid(identityDocument);
    }

    private boolean cacheValid(Map<String, Object> identityDocument) {
        String validUntil = asString(identityDocument.get("valid_until"));
        if (validUntil == null) {
            return false;
        }
        try {
            return Instant.parse(validUntil).isAfter(Instant.now());
        } catch (Exception exc) {
            return false;
        }
    }

    private void cacheIdentity(String agentId, Map<String, Object> identityDocument) {
        cache.put(agentId, new CachedDocument(identityDocument, Instant.now().toString()));
        persistCache();
    }

    private void loadCache() {
        if (cachePath == null || !Files.exists(cachePath)) {
            return;
        }
        try {
            Map<String, CachedDocument> raw = JsonSupport.mapper().readValue(
                Files.readString(cachePath),
                new TypeReference<Map<String, CachedDocument>>() {
                }
            );
            cache.putAll(raw);
        } catch (Exception exc) {
            cache.clear();
        }
    }

    private void persistCache() {
        if (cachePath == null) {
            return;
        }
        try {
            Files.createDirectories(cachePath.getParent());
            Files.writeString(cachePath, JsonSupport.toJson(new HashMap<>(cache)));
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to persist discovery cache", exc);
        }
    }

    private static String withQuery(String baseUrl, Map<String, String> queryParams) {
        StringBuilder query = new StringBuilder(baseUrl);
        query.append(baseUrl.contains("?") ? "&" : "?");
        boolean first = true;
        for (Map.Entry<String, String> entry : queryParams.entrySet()) {
            if (!first) {
                query.append("&");
            }
            first = false;
            query.append(URLEncoder.encode(entry.getKey(), StandardCharsets.UTF_8));
            query.append("=");
            query.append(URLEncoder.encode(entry.getValue(), StandardCharsets.UTF_8));
        }
        return query.toString();
    }

    private static String asString(Object value) {
        return value instanceof String str ? str : null;
    }

    public record CachedDocument(
        @com.fasterxml.jackson.annotation.JsonProperty("identity_document")
        Map<String, Object> identityDocument,
        @com.fasterxml.jackson.annotation.JsonProperty("fetched_at")
        String fetchedAt
    ) {
    }
}
