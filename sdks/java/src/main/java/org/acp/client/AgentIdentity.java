package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class AgentIdentity {
    private static final String IDENTITY_FILE_NAME = "identity.json";
    private static final String IDENTITY_DOC_FILE_NAME = "identity_document.json";
    private static final Pattern AGENT_ID_PATTERN = Pattern.compile("^agent:(?<name>[^@]+)(?:@(?<domain>.+))?$");

    @JsonProperty("agent_id")
    private String agentId;
    @JsonProperty("signing_private_key")
    private String signingPrivateKey;
    @JsonProperty("signing_public_key")
    private String signingPublicKey;
    @JsonProperty("encryption_private_key")
    private String encryptionPrivateKey;
    @JsonProperty("encryption_public_key")
    private String encryptionPublicKey;
    @JsonProperty("signing_kid")
    private String signingKid;
    @JsonProperty("encryption_kid")
    private String encryptionKid;

    public AgentIdentity() {
    }

    public static AgentIdentity create(String agentId) {
        parseAgentId(agentId);
        CryptoSupport.KeyMaterial signing = CryptoSupport.generateEd25519Keypair();
        CryptoSupport.KeyMaterial encryption = CryptoSupport.generateX25519Keypair();

        AgentIdentity identity = new AgentIdentity();
        identity.agentId = agentId;
        identity.signingPrivateKey = signing.privateKey();
        identity.signingPublicKey = signing.publicKey();
        identity.encryptionPrivateKey = encryption.privateKey();
        identity.encryptionPublicKey = encryption.publicKey();
        identity.signingKid = "sig-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        identity.encryptionKid = "enc-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        return identity;
    }

    public Map<String, Object> buildIdentityDocument(
        String directEndpoint,
        List<String> relayHints,
        String trustProfile,
        Map<String, Object> capabilities,
        int validDays
    ) {
        return buildIdentityDocument(
            directEndpoint,
            relayHints,
            trustProfile,
            capabilities,
            validDays,
            null,
            null
        );
    }

    public Map<String, Object> buildIdentityDocument(
        String directEndpoint,
        List<String> relayHints,
        String trustProfile,
        Map<String, Object> capabilities,
        int validDays,
        Map<String, Object> amqpService
    ) {
        return buildIdentityDocument(
            directEndpoint,
            relayHints,
            trustProfile,
            capabilities,
            validDays,
            amqpService,
            null
        );
    }

    public Map<String, Object> buildIdentityDocument(
        String directEndpoint,
        List<String> relayHints,
        String trustProfile,
        Map<String, Object> capabilities,
        int validDays,
        Map<String, Object> amqpService,
        Map<String, Object> mqttService
    ) {
        if (!AcpConstants.TRUST_PROFILES.contains(trustProfile)) {
            throw new IllegalArgumentException("Unsupported trust profile: " + trustProfile);
        }
        Map<String, Object> document = new HashMap<>();
        document.put("acp_identity_version", AcpConstants.ACP_IDENTITY_VERSION);
        document.put("agent_id", agentId);
        document.put("created_at", Instant.now().toString());
        document.put("valid_until", Instant.now().plus(validDays, ChronoUnit.DAYS).toString());
        document.put("trust_profile", trustProfile);

        Map<String, Object> keys = new HashMap<>();
        keys.put(
            "signing",
            Map.of(
                "kid", signingKid,
                "alg", "Ed25519",
                "public_key", signingPublicKey
            )
        );
        keys.put(
            "encryption",
            Map.of(
                "kid", encryptionKid,
                "alg", "X25519",
                "public_key", encryptionPublicKey
            )
        );
        document.put("keys", keys);
        Map<String, Object> service = new HashMap<>();
        service.put("direct_endpoint", directEndpoint);
        service.put("relay_hints", relayHints == null ? List.of() : new ArrayList<>(relayHints));
        if (amqpService != null && !amqpService.isEmpty()) {
            service.put("amqp", new HashMap<>(amqpService));
        }
        if (mqttService != null && !mqttService.isEmpty()) {
            service.put("mqtt", new HashMap<>(mqttService));
        }
        document.put(
            "service",
            service
        );
        document.put("capabilities", capabilities == null ? Map.of() : capabilities);

        String signature = CryptoSupport.signBytes(CanonicalJson.bytes(document), signingPrivateKey);
        document.put(
            "signature",
            Map.of(
                "algorithm", "Ed25519",
                "signed_by", signingKid,
                "value", signature
            )
        );
        return document;
    }

    public static boolean verifyIdentityDocument(Map<String, Object> identityDocument) {
        for (String required : List.of("agent_id", "keys", "service", "signature", "valid_until")) {
            if (!identityDocument.containsKey(required)) {
                return false;
            }
        }

        Object trustProfile = identityDocument.get("trust_profile");
        if (!(trustProfile instanceof String profile) || !AcpConstants.TRUST_PROFILES.contains(profile)) {
            return false;
        }

        String validUntil = asString(identityDocument.get("valid_until"));
        if (validUntil == null) {
            return false;
        }
        try {
            if (!Instant.parse(validUntil).isAfter(Instant.now())) {
                return false;
            }
        } catch (Exception exc) {
            return false;
        }

        Map<String, Object> signature = asMap(identityDocument.get("signature"));
        String signatureValue = asString(signature.get("value"));
        Map<String, Object> keys = asMap(identityDocument.get("keys"));
        Map<String, Object> signing = asMap(keys.get("signing"));
        String signingPublicKey = asString(signing.get("public_key"));
        if (signatureValue == null || signingPublicKey == null) {
            return false;
        }

        Map<String, Object> unsigned = new HashMap<>(identityDocument);
        unsigned.remove("signature");
        return CryptoSupport.verifySignature(
            CanonicalJson.bytes(unsigned),
            signatureValue,
            signingPublicKey
        );
    }

    public static IdentityBundle readIdentity(Path storageDir, String agentId) {
        Path agentDir = identityPath(storageDir, agentId);
        Path identityPath = agentDir.resolve(IDENTITY_FILE_NAME);
        Path documentPath = agentDir.resolve(IDENTITY_DOC_FILE_NAME);
        if (!Files.exists(identityPath) || !Files.exists(documentPath)) {
            return null;
        }
        try {
            AgentIdentity identity = JsonSupport.fromJson(Files.readString(identityPath), AgentIdentity.class);
            Map<String, Object> document = JsonSupport.mapFromJson(Files.readString(documentPath));
            return new IdentityBundle(identity, document);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to load local identity", exc);
        }
    }

    public static void writeIdentity(Path storageDir, AgentIdentity identity, Map<String, Object> identityDocument) {
        try {
            Path agentDir = identityPath(storageDir, identity.agentId);
            Files.createDirectories(agentDir);
            Files.writeString(agentDir.resolve(IDENTITY_FILE_NAME), CanonicalJson.stringify(JsonSupport.toMap(identity)));
            Files.writeString(agentDir.resolve(IDENTITY_DOC_FILE_NAME), CanonicalJson.stringify(identityDocument));
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to persist local identity", exc);
        }
    }

    public static AgentIdParts parseAgentId(String agentId) {
        Matcher matcher = AGENT_ID_PATTERN.matcher(agentId);
        if (!matcher.matches()) {
            throw new IllegalArgumentException("Invalid agent identifier: " + agentId);
        }
        return new AgentIdParts(matcher.group("name"), matcher.group("domain"));
    }

    public static Path identityPath(Path storageDir, String agentId) {
        return storageDir.resolve(sanitizeAgentId(agentId));
    }

    public static String sanitizeAgentId(String agentId) {
        return agentId.replaceAll("[^a-zA-Z0-9._-]", "_");
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return Map.of();
    }

    private static String asString(Object value) {
        return value instanceof String str ? str : null;
    }

    public String getAgentId() {
        return agentId;
    }

    public void setAgentId(String agentId) {
        this.agentId = agentId;
    }

    public String getSigningPrivateKey() {
        return signingPrivateKey;
    }

    public void setSigningPrivateKey(String signingPrivateKey) {
        this.signingPrivateKey = signingPrivateKey;
    }

    public String getSigningPublicKey() {
        return signingPublicKey;
    }

    public void setSigningPublicKey(String signingPublicKey) {
        this.signingPublicKey = signingPublicKey;
    }

    public String getEncryptionPrivateKey() {
        return encryptionPrivateKey;
    }

    public void setEncryptionPrivateKey(String encryptionPrivateKey) {
        this.encryptionPrivateKey = encryptionPrivateKey;
    }

    public String getEncryptionPublicKey() {
        return encryptionPublicKey;
    }

    public void setEncryptionPublicKey(String encryptionPublicKey) {
        this.encryptionPublicKey = encryptionPublicKey;
    }

    public String getSigningKid() {
        return signingKid;
    }

    public void setSigningKid(String signingKid) {
        this.signingKid = signingKid;
    }

    public String getEncryptionKid() {
        return encryptionKid;
    }

    public void setEncryptionKid(String encryptionKid) {
        this.encryptionKid = encryptionKid;
    }

    public record AgentIdParts(String name, String domain) {
    }

    public record IdentityBundle(AgentIdentity identity, Map<String, Object> identityDocument) {
    }
}
