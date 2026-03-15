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
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class DiscoveryClient {
    private static final String WELL_KNOWN_PATH = "/.well-known/acp";
    private static final String WELL_KNOWN_VERSION = "1.0";

    private final Path cachePath;
    private final String defaultScheme;
    private final List<String> relayHints;
    private final List<String> enterpriseDirectoryHints;
    private final int timeoutSeconds;
    private final boolean allowInsecureHttp;
    private final boolean mtlsEnabled;
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
        this(
            cachePath,
            defaultScheme,
            relayHints,
            enterpriseDirectoryHints,
            timeoutSeconds,
            false,
            false,
            null,
            false,
            null,
            null
        );
    }

    public DiscoveryClient(
        Path cachePath,
        String defaultScheme,
        List<String> relayHints,
        List<String> enterpriseDirectoryHints,
        int timeoutSeconds,
        boolean allowInsecureHttp,
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile
    ) {
        this.cachePath = cachePath;
        this.defaultScheme = defaultScheme == null ? "https" : defaultScheme;
        this.relayHints = relayHints == null ? List.of() : List.copyOf(relayHints);
        this.enterpriseDirectoryHints = enterpriseDirectoryHints == null ? List.of() : List.copyOf(enterpriseDirectoryHints);
        this.timeoutSeconds = timeoutSeconds <= 0 ? 5 : timeoutSeconds;
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

    public Map<String, Object> resolveWellKnown(String baseUrl, String expectedAgentId) {
        String wellKnownUrl = normalizedWellKnownUrl(baseUrl);
        Map<String, Object> resolved = resolveWellKnownUrl(wellKnownUrl, expectedAgentId);
        if (resolved == null) {
            throw new IllegalStateException("Unable to resolve well-known metadata from " + wellKnownUrl);
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> identityDocument = (Map<String, Object>) resolved.get("identity_document");
        String agentId = asString(identityDocument.get("agent_id"));
        if (isBlank(agentId)) {
            throw new IllegalStateException("Well-known discovery returned identity document without agent_id");
        }
        cacheIdentity(agentId, identityDocument);
        resolved.put("well_known_url", wellKnownUrl);
        return resolved;
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
        String url = defaultScheme + "://" + parts.domain() + WELL_KNOWN_PATH;
        Map<String, Object> resolved = resolveWellKnownUrl(url, agentId);
        if (resolved == null) {
            return null;
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> identityDocument = (Map<String, Object>) resolved.get("identity_document");
        return identityDocument;
    }

    private Map<String, Object> tryHintLookups(List<String> hints, String agentId) {
        for (String hint : hints) {
            String base = hint.endsWith("/") ? hint.substring(0, hint.length() - 1) : hint;
            Map<String, Object> value = fetchIdentityDocument(base + "/discover", Map.of("agent_id", agentId), "Discovery hint lookup");
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private Map<String, Object> resolveWellKnownUrl(String wellKnownUrl, String expectedAgentId) {
        Map<String, Object> wellKnown = fetchJson(wellKnownUrl, null, "Discovery .well-known lookup");
        if (!isValidWellKnownDocument(wellKnown)) {
            return null;
        }
        if (!isBlank(expectedAgentId) && !expectedAgentId.equals(asString(wellKnown.get("agent_id")))) {
            return null;
        }
        Object identityReference = wellKnown.get("identity_document");
        Map<String, Object> identityDocument;
        if (identityReference instanceof String reference && !reference.isBlank()) {
            String resolvedReference = resolveReference(wellKnownUrl, reference);
            identityDocument = fetchIdentityDocument(
                resolvedReference,
                null,
                "Discovery identity document lookup"
            );
        } else {
            return null;
        }
        if (identityDocument == null) {
            return null;
        }
        if (!validateIdentityDocument(identityDocument)) {
            return null;
        }
        if (!isBlank(expectedAgentId) && !expectedAgentId.equals(asString(identityDocument.get("agent_id")))) {
            return null;
        }
        Map<String, Object> result = new HashMap<>();
        result.put("well_known", wellKnown);
        result.put("identity_document", identityDocument);
        return result;
    }

    private Map<String, Object> fetchIdentityDocument(String url, Map<String, String> queryParams, String context) {
        Map<String, Object> body = fetchJson(url, queryParams, context);
        if (body == null) {
            return null;
        }
        return extractIdentityDocument(body);
    }

    private Map<String, Object> fetchJson(String url, Map<String, String> queryParams, String context) {
        try {
            URI uri = HttpSecurity.validateHttpUrl(
                queryParams == null ? url : withQuery(url, queryParams),
                allowInsecureHttp,
                mtlsEnabled,
                context
            );
            HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                return null;
            }
            return JsonSupport.mapFromJson(response.body());
        } catch (Exception exc) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> extractIdentityDocument(Map<String, Object> body) {
        Object identityDocument = body.get("identity_document");
        if (identityDocument == null && body.containsKey("agent_id")) {
            identityDocument = body;
        }
        if (identityDocument instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return null;
    }

    private boolean isValidWellKnownDocument(Map<String, Object> value) {
        if (value == null) {
            return false;
        }
        if (isBlank(asString(value.get("agent_id")))) {
            return false;
        }
        try {
            AgentIdentity.parseAgentId(asString(value.get("agent_id")));
        } catch (Exception exc) {
            return false;
        }
        if (!(value.get("transports") instanceof Map<?, ?>)) {
            return false;
        }
        if (!WELL_KNOWN_VERSION.equals(asString(value.get("version")))) {
            return false;
        }
        Object identityReference = value.get("identity_document");
        if (!(identityReference instanceof String reference) || isBlank(reference)) {
            return false;
        }
        if (!isValidIdentityReference(reference)) {
            return false;
        }
        String securityProfile = asString(value.get("security_profile"));
        if (!isBlank(securityProfile) && !Set.of("http", "https", "mtls", "https+mtls").contains(securityProfile)) {
            return false;
        }
        return areTransportHintsValid(value.get("transports"));
    }

    private static boolean isValidIdentityReference(String reference) {
        try {
            URI uri = URI.create(reference);
            if (uri.isAbsolute()) {
                String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
                return Set.of("http", "https").contains(scheme) && !isBlank(uri.getHost());
            }
            return reference.startsWith("/");
        } catch (Exception exc) {
            return false;
        }
    }

    @SuppressWarnings("unchecked")
    private static boolean areTransportHintsValid(Object rawTransports) {
        if (!(rawTransports instanceof Map<?, ?> raw)) {
            return false;
        }
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getValue() instanceof Map<?, ?> hintRaw)) {
                return false;
            }
            Map<String, Object> hint = (Map<String, Object>) hintRaw;
            Object endpointRaw = hint.get("endpoint");
            if (endpointRaw != null) {
                if (!(endpointRaw instanceof String endpoint) || !isValidHttpEndpoint(endpoint)) {
                    return false;
                }
            }
            String profile = asString(hint.get("security_profile"));
            if (!isBlank(profile) && !Set.of("http", "https", "mtls", "https+mtls").contains(profile)) {
                return false;
            }
        }
        return true;
    }

    private static boolean isValidHttpEndpoint(String endpoint) {
        try {
            URI uri = URI.create(endpoint);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
            return Set.of("http", "https").contains(scheme) && !isBlank(uri.getHost());
        } catch (Exception exc) {
            return false;
        }
    }

    private static String normalizedWellKnownUrl(String baseUrl) {
        if (isBlank(baseUrl)) {
            throw new IllegalArgumentException("baseUrl is required");
        }
        String normalized = baseUrl.trim();
        if (normalized.endsWith(WELL_KNOWN_PATH)) {
            return normalized;
        }
        return normalized.replaceAll("/+$", "") + WELL_KNOWN_PATH;
    }

    private static String resolveReference(String sourceUrl, String reference) {
        try {
            URI ref = URI.create(reference);
            if (ref.isAbsolute()) {
                return reference;
            }
            return URI.create(sourceUrl).resolve(ref).toString();
        } catch (Exception exc) {
            return reference;
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

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    public record CachedDocument(
        @com.fasterxml.jackson.annotation.JsonProperty("identity_document")
        Map<String, Object> identityDocument,
        @com.fasterxml.jackson.annotation.JsonProperty("fetched_at")
        String fetchedAt
    ) {
    }
}
