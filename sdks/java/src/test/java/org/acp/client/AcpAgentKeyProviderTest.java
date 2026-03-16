package org.acp.client;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AcpAgentKeyProviderTest {
    @Test
    void agentUsesVaultProviderForHttpsTrustMaterial(@TempDir Path tempDir) throws Exception {
        String agentId = "agent:vault.trust@localhost:9950";
        AgentIdentity seeded = AgentIdentity.create(agentId);
        String payload = vaultPayload(seeded, resourcePath("tls/test-ca.pem").toString(), null, null);
        AtomicReference<String> seenToken = new AtomicReference<>();
        HttpServer server = startVaultServer(payload, seenToken);
        try {
            AcpAgent agent = AcpAgent.loadOrCreate(
                agentId,
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("vault-agent"))
                    .setEndpoint("https://localhost:9950/acp/inbox")
                    .setKeyProvider("vault")
                    .setVaultUrl("http://127.0.0.1:" + server.getAddress().getPort())
                    .setVaultPath("secret/data/acp/identities")
                    .setVaultToken("token-123")
                    .setAllowInsecureHttp(true)
            );
            assertNotNull(agent);
            assertEquals("vault", agent.getKeyProviderInfo().get("provider"));
            AgentIdentity.IdentityBundle bundle = AgentIdentity.readIdentity(tempDir.resolve("vault-agent"), agentId);
            assertNotNull(bundle);
            assertEquals(seeded.getSigningPrivateKey(), bundle.identity().getSigningPrivateKey());
            assertEquals("token-123", seenToken.get());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void agentLoadsMtlsMaterialsFromVaultProvider(@TempDir Path tempDir) throws Exception {
        String agentId = "agent:vault.mtls@localhost:9951";
        AgentIdentity seeded = AgentIdentity.create(agentId);
        String payload = vaultPayload(
            seeded,
            resourcePath("tls/test-ca.pem").toString(),
            resourcePath("tls/test-client-cert.pem").toString(),
            resourcePath("tls/test-client-key.pem").toString()
        );
        HttpServer server = startVaultServer(payload, new AtomicReference<>());
        try {
            AcpAgent agent = AcpAgent.loadOrCreate(
                agentId,
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("vault-mtls-agent"))
                    .setEndpoint("https://localhost:9951/acp/inbox")
                    .setMtlsEnabled(true)
                    .setKeyProvider("vault")
                    .setVaultUrl("http://127.0.0.1:" + server.getAddress().getPort())
                    .setVaultPath("secret/data/acp/identities")
                    .setVaultToken("token-123")
                    .setAllowInsecureHttp(true)
            );
            assertNotNull(agent);
            assertEquals("vault", agent.getKeyProviderInfo().get("provider"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void rejectsInvalidVaultProviderConfiguration(@TempDir Path tempDir) {
        IllegalStateException missingVaultUrl = assertThrows(
            IllegalStateException.class,
            () -> AcpAgent.loadOrCreate(
                "agent:vault.invalid@localhost:9952",
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("invalid-vault"))
                    .setKeyProvider("vault")
                    .setVaultPath("secret/data/acp/identities")
            )
        );
        assertTrue(missingVaultUrl.getMessage().contains("vaultUrl is required"));

        IllegalStateException unsupported = assertThrows(
            IllegalStateException.class,
            () -> AcpAgent.loadOrCreate(
                "agent:vault.unsupported@localhost:9953",
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("unsupported-vault"))
                    .setKeyProvider("kms")
            )
        );
        assertTrue(unsupported.getMessage().contains("Unsupported keyProvider"));
    }

    @Test
    void rejectsMtlsWhenVaultProviderMissingClientCertificate(@TempDir Path tempDir) throws Exception {
        String agentId = "agent:vault.mtls.missing@localhost:9954";
        AgentIdentity seeded = AgentIdentity.create(agentId);
        String payload = vaultPayload(seeded, resourcePath("tls/test-ca.pem").toString(), null, null);
        HttpServer server = startVaultServer(payload, new AtomicReference<>());
        try {
            IllegalStateException exc = assertThrows(
                IllegalStateException.class,
                () -> AcpAgent.loadOrCreate(
                    agentId,
                    new AcpAgentOptions()
                        .setStorageDir(tempDir.resolve("vault-mtls-missing"))
                        .setEndpoint("https://localhost:9954/acp/inbox")
                        .setMtlsEnabled(true)
                        .setKeyProvider("vault")
                        .setVaultUrl("http://127.0.0.1:" + server.getAddress().getPort())
                        .setVaultPath("secret/data/acp/identities")
                        .setVaultToken("token-123")
                        .setAllowInsecureHttp(true)
                )
            );
            assertTrue(exc.getMessage().contains("certFile"));
        } finally {
            server.stop(0);
        }
    }

    private static HttpServer startVaultServer(String payload, AtomicReference<String> seenToken) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
            "/v1/secret/data/acp/identities",
            exchange -> {
                seenToken.set(exchange.getRequestHeaders().getFirst("X-Vault-Token"));
                byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
                exchange.close();
            }
        );
        server.start();
        return server;
    }

    private static String vaultPayload(AgentIdentity identity, String caFile, String certFile, String keyFile) {
        Map<String, Object> secret = new LinkedHashMap<>();
        secret.put("signing_key", identity.getSigningPrivateKey());
        secret.put("encryption_key", identity.getEncryptionPrivateKey());
        secret.put("signing_public_key", identity.getSigningPublicKey());
        secret.put("encryption_public_key", identity.getEncryptionPublicKey());
        secret.put("signing_kid", identity.getSigningKid());
        secret.put("encryption_kid", identity.getEncryptionKid());
        if (caFile != null) {
            secret.put("ca_file", caFile);
        }
        if (certFile != null) {
            secret.put("tls_cert_file", certFile);
        }
        if (keyFile != null) {
            secret.put("tls_key_file", keyFile);
        }
        return JsonSupport.toJson(Map.of("data", Map.of("data", secret)));
    }

    private static Path resourcePath(String resource) {
        try {
            return Path.of(AcpAgentKeyProviderTest.class.getClassLoader().getResource(resource).toURI());
        } catch (Exception exc) {
            throw new IllegalStateException("Missing test resource: " + resource, exc);
        }
    }
}
