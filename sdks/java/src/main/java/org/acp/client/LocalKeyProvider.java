package org.acp.client;

import java.nio.file.Path;
import java.util.Map;

public class LocalKeyProvider implements KeyProvider {
    private final Path storageDir;
    private final String certFile;
    private final String keyFile;
    private final String caFile;

    public LocalKeyProvider(Path storageDir, String certFile, String keyFile, String caFile) {
        this.storageDir = storageDir;
        this.certFile = normalizeOptional(certFile);
        this.keyFile = normalizeOptional(keyFile);
        this.caFile = normalizeOptional(caFile);
    }

    @Override
    public IdentityKeyMaterial loadIdentityKeys(String agentId) {
        AgentIdentity.IdentityBundle bundle = AgentIdentity.readIdentity(storageDir, agentId);
        if (bundle == null) {
            throw new KeyProviderException("Local identity not found for " + agentId);
        }
        AgentIdentity identity = bundle.identity();
        return new IdentityKeyMaterial(
            identity.getSigningPrivateKey(),
            identity.getEncryptionPrivateKey(),
            identity.getSigningPublicKey(),
            identity.getEncryptionPublicKey(),
            identity.getSigningKid(),
            identity.getEncryptionKid()
        );
    }

    @Override
    public TlsMaterial loadTlsMaterial(String agentId) {
        return new TlsMaterial(certFile, keyFile, caFile);
    }

    @Override
    public String loadCaBundle(String agentId) {
        return caFile;
    }

    @Override
    public Map<String, Object> describe() {
        return Map.of(
            "provider", "local",
            "storage_dir", storageDir.toString()
        );
    }

    private static String normalizeOptional(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
