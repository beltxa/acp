package org.acp.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class VaultKeyProvider implements KeyProvider {
    private final String vaultUrl;
    private final String vaultPath;
    private final String vaultTokenEnv;
    private final String token;
    private final int timeoutSeconds;
    private final HttpClient httpClient;
    private final Map<String, Map<String, Object>> cache = new ConcurrentHashMap<>();

    public VaultKeyProvider(
        String vaultUrl,
        String vaultPath,
        String vaultTokenEnv,
        String token,
        int timeoutSeconds,
        String caFile,
        boolean allowInsecureTls,
        boolean allowInsecureHttp
    ) {
        this.vaultUrl = trimAndRequire(vaultUrl, "vaultUrl").replaceAll("/+$", "");
        this.vaultPath = trimAndRequire(vaultPath, "vaultPath").replaceAll("^/+|/+$", "");
        this.vaultTokenEnv = normalizeOptional(vaultTokenEnv) == null ? "VAULT_TOKEN" : vaultTokenEnv.trim();
        this.token = normalizeOptional(token);
        this.timeoutSeconds = timeoutSeconds <= 0 ? 5 : timeoutSeconds;
        HttpSecurity.validateHttpUrl(this.vaultUrl, allowInsecureHttp, false, "Vault key provider URL");
        this.httpClient = HttpSecurity.buildHttpClient(
            this.timeoutSeconds,
            allowInsecureTls,
            normalizeOptional(caFile),
            false,
            null,
            null
        );
    }

    @Override
    public IdentityKeyMaterial loadIdentityKeys(String agentId) {
        Map<String, Object> secret = loadSecret(agentId);
        String signingPrivate = secretValue(secret, "signing_key", "identity_signing_key", "signing_private_key");
        String encryptionPrivate = secretValue(
            secret,
            "encryption_key",
            "identity_encryption_key",
            "encryption_private_key"
        );
        if (signingPrivate == null) {
            throw new KeyProviderException("Vault secret for " + agentId + " is missing signing_key");
        }
        if (encryptionPrivate == null) {
            throw new KeyProviderException("Vault secret for " + agentId + " is missing encryption_key");
        }
        return new IdentityKeyMaterial(
            signingPrivate,
            encryptionPrivate,
            secretValue(secret, "signing_public_key"),
            secretValue(secret, "encryption_public_key"),
            secretValue(secret, "signing_kid"),
            secretValue(secret, "encryption_kid")
        );
    }

    @Override
    public TlsMaterial loadTlsMaterial(String agentId) {
        Map<String, Object> secret = loadSecret(agentId);
        return new TlsMaterial(
            secretValue(secret, "tls_cert_file", "tls_cert", "cert_file"),
            secretValue(secret, "tls_key_file", "tls_key", "key_file"),
            secretValue(secret, "ca_bundle_file", "ca_file", "ca_bundle")
        );
    }

    @Override
    public String loadCaBundle(String agentId) {
        Map<String, Object> secret = loadSecret(agentId);
        return secretValue(secret, "ca_bundle_file", "ca_file", "ca_bundle");
    }

    @Override
    public Map<String, Object> describe() {
        return Map.of(
            "provider", "vault",
            "vault_url", vaultUrl,
            "vault_path", vaultPath,
            "vault_token_env", vaultTokenEnv
        );
    }

    private Map<String, Object> loadSecret(String agentId) {
        String path = secretPath(agentId);
        Map<String, Object> cached = cache.get(path);
        if (cached != null) {
            return cached;
        }

        String resolvedToken = resolveToken();
        if (resolvedToken == null) {
            throw new KeyProviderException(
                "Vault token is missing. Set token or environment variable " + vaultTokenEnv + "."
            );
        }

        String url = vaultUrl + "/v1/" + path.replaceFirst("^/+", "");
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .header("Accept", "application/json")
            .header("X-Vault-Token", resolvedToken)
            .GET()
            .build();

        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception exc) {
            throw new KeyProviderException("Vault request failed for path " + path + ": " + exc.getMessage(), exc);
        }
        if (response.statusCode() != 200) {
            throw new KeyProviderException(
                "Vault returned HTTP " + response.statusCode() + " for path " + path
            );
        }

        Map<String, Object> payload;
        try {
            payload = JsonSupport.mapFromJson(response.body() == null ? "{}" : response.body());
        } catch (Exception exc) {
            throw new KeyProviderException("Vault returned non-JSON response for path " + path, exc);
        }
        Map<String, Object> secret = extractSecretData(payload, path);
        cache.put(path, secret);
        return secret;
    }

    private Map<String, Object> extractSecretData(Map<String, Object> payload, String path) {
        Map<String, Object> data = asMap(payload.get("data"));
        if (data.isEmpty()) {
            throw new KeyProviderException("Vault response for path " + path + " is missing data object");
        }
        Map<String, Object> nestedData = asMap(data.get("data"));
        if (!nestedData.isEmpty()) {
            return nestedData;
        }
        return data;
    }

    private String secretPath(String agentId) {
        if (vaultPath.contains("{agent_id}")) {
            return vaultPath.replace("{agent_id}", AgentIdentity.sanitizeAgentId(agentId == null ? "" : agentId));
        }
        if (agentId == null || agentId.isBlank()) {
            return vaultPath;
        }
        return vaultPath + "/" + AgentIdentity.sanitizeAgentId(agentId);
    }

    private String resolveToken() {
        if (token != null) {
            return token;
        }
        String envValue = System.getenv(vaultTokenEnv);
        return normalizeOptional(envValue);
    }

    private static String secretValue(Map<String, Object> secret, String... keys) {
        for (String key : keys) {
            Object value = secret.get(key);
            if (value instanceof String str && !str.isBlank()) {
                return str.trim();
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return Map.of();
    }

    private static String trimAndRequire(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new KeyProviderException(label + " is required for VaultKeyProvider");
        }
        return value.trim();
    }

    private static String normalizeOptional(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
