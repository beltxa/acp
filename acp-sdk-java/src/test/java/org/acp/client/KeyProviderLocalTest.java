package org.acp.client;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class KeyProviderLocalTest {
    @Test
    void localKeyProviderReadsIdentityAndTlsMaterial(@TempDir Path tempDir) {
        String agentId = "agent:key.local@test";
        AgentIdentity identity = AgentIdentity.create(agentId);
        Map<String, Object> document = identity.buildIdentityDocument(
            null,
            java.util.List.of(),
            "self_asserted",
            Map.of("agent_id", agentId),
            365
        );
        AgentIdentity.writeIdentity(tempDir, identity, document);

        LocalKeyProvider provider = new LocalKeyProvider(
            tempDir,
            "/tmp/client-cert.pem",
            "/tmp/client-key.pem",
            "/tmp/ca.pem"
        );
        IdentityKeyMaterial keys = provider.loadIdentityKeys(agentId);
        TlsMaterial tlsMaterial = provider.loadTlsMaterial(agentId);

        assertEquals(identity.getSigningPrivateKey(), keys.getSigningPrivateKey());
        assertEquals(identity.getEncryptionPrivateKey(), keys.getEncryptionPrivateKey());
        assertEquals(identity.getSigningPublicKey(), keys.getSigningPublicKey());
        assertEquals(identity.getEncryptionPublicKey(), keys.getEncryptionPublicKey());
        assertEquals(identity.getSigningKid(), keys.getSigningKid());
        assertEquals(identity.getEncryptionKid(), keys.getEncryptionKid());
        assertEquals("/tmp/client-cert.pem", tlsMaterial.getCertFile());
        assertEquals("/tmp/client-key.pem", tlsMaterial.getKeyFile());
        assertEquals("/tmp/ca.pem", tlsMaterial.getCaFile());
        assertEquals("local", provider.describe().get("provider"));
    }

    @Test
    void localKeyProviderFailsForMissingIdentity(@TempDir Path tempDir) {
        LocalKeyProvider provider = new LocalKeyProvider(tempDir, null, null, null);
        KeyProviderException exc = assertThrows(
            KeyProviderException.class,
            () -> provider.loadIdentityKeys("agent:missing@test")
        );
        org.junit.jupiter.api.Assertions.assertTrue(exc.getMessage().contains("Local identity not found"));
    }
}
