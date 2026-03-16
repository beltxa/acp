package org.acp.client;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VaultKeyProviderTest {
    @Test
    void vaultKeyProviderLoadsIdentityAndTlsMaterial() throws Exception {
        AtomicReference<String> seenToken = new AtomicReference<>();
        AtomicReference<String> seenPath = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
            "/v1/secret/data/acp/identities",
            exchange -> {
                seenToken.set(exchange.getRequestHeaders().getFirst("X-Vault-Token"));
                seenPath.set(exchange.getRequestURI().getPath());
                String body = """
                    {"data":{"data":{
                      "signing_key":"sig-private",
                      "encryption_key":"enc-private",
                      "signing_public_key":"sig-public",
                      "encryption_public_key":"enc-public",
                      "signing_kid":"sig-kid",
                      "encryption_kid":"enc-kid",
                      "ca_file":"/etc/acp/ca.pem",
                      "tls_cert_file":"/etc/acp/client-cert.pem",
                      "tls_key_file":"/etc/acp/client-key.pem"
                    }}}""";
                byte[] payload = body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, payload.length);
                exchange.getResponseBody().write(payload);
                exchange.close();
            }
        );
        server.start();
        try {
            String vaultUrl = "http://127.0.0.1:" + server.getAddress().getPort();
            VaultKeyProvider provider = new VaultKeyProvider(
                vaultUrl,
                "secret/data/acp/identities",
                "UNUSED_TOKEN_ENV",
                "token-abc",
                5,
                null,
                false,
                true
            );
            IdentityKeyMaterial keys = provider.loadIdentityKeys("agent:john.chess@demo");
            TlsMaterial tlsMaterial = provider.loadTlsMaterial("agent:john.chess@demo");

            assertEquals("token-abc", seenToken.get());
            assertTrue(seenPath.get().endsWith("/v1/secret/data/acp/identities/agent_john.chess_demo"));
            assertEquals("sig-private", keys.getSigningPrivateKey());
            assertEquals("enc-private", keys.getEncryptionPrivateKey());
            assertEquals("sig-public", keys.getSigningPublicKey());
            assertEquals("enc-public", keys.getEncryptionPublicKey());
            assertEquals("sig-kid", keys.getSigningKid());
            assertEquals("enc-kid", keys.getEncryptionKid());
            assertEquals("/etc/acp/ca.pem", tlsMaterial.getCaFile());
            assertEquals("/etc/acp/client-cert.pem", tlsMaterial.getCertFile());
            assertEquals("/etc/acp/client-key.pem", tlsMaterial.getKeyFile());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void vaultKeyProviderFailsWhenTokenIsMissing() {
        VaultKeyProvider provider = new VaultKeyProvider(
            "https://vault.example",
            "secret/data/acp/identities",
            "ACP_TEST_MISSING_TOKEN",
            null,
            5,
            null,
            false,
            false
        );
        KeyProviderException exc = assertThrows(
            KeyProviderException.class,
            () -> provider.loadIdentityKeys("agent:john@demo")
        );
        assertTrue(exc.getMessage().contains("Vault token is missing"));
    }

    @Test
    void vaultKeyProviderFailsWhenSecretMissingRequiredFields() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
            "/v1/secret/data/acp/identities",
            exchange -> {
                String body = "{\"data\":{\"data\":{\"encryption_key\":\"enc-only\"}}}";
                byte[] payload = body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, payload.length);
                exchange.getResponseBody().write(payload);
                exchange.close();
            }
        );
        server.start();
        try {
            String vaultUrl = "http://127.0.0.1:" + server.getAddress().getPort();
            VaultKeyProvider provider = new VaultKeyProvider(
                vaultUrl,
                "secret/data/acp/identities",
                "UNUSED_TOKEN_ENV",
                "token-abc",
                5,
                null,
                false,
                true
            );
            KeyProviderException exc = assertThrows(
                KeyProviderException.class,
                () -> provider.loadIdentityKeys("agent:john@demo")
            );
            assertTrue(exc.getMessage().contains("missing signing_key"));
        } finally {
            server.stop(0);
        }
    }
}
