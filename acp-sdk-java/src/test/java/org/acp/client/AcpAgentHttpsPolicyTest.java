package org.acp.client;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AcpAgentHttpsPolicyTest {
    @Test
    void rejectsInsecureHttpEndpointByDefault(@TempDir Path tempDir) {
        IllegalStateException exc = assertThrows(
            IllegalStateException.class,
            () -> AcpAgent.loadOrCreate(
                "agent:https.policy@localhost:9900",
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("agent"))
                    .setEndpoint("http://localhost:9900/acp/inbox")
            )
        );
        org.junit.jupiter.api.Assertions.assertTrue(exc.getMessage().contains("insecure HTTP"));
    }

    @Test
    void allowsInsecureHttpWhenExplicitlyEnabled(@TempDir Path tempDir) {
        assertDoesNotThrow(() ->
            AcpAgent.loadOrCreate(
                "agent:https.policy.dev@localhost:9901",
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("agent-dev"))
                    .setEndpoint("http://localhost:9901/acp/inbox")
                    .setAllowInsecureHttp(true)
                    .setDiscoveryScheme("http")
            )
        );
    }

    @Test
    void rejectsMtlsWithoutClientCertificate(@TempDir Path tempDir) {
        IllegalStateException exc = assertThrows(
            IllegalStateException.class,
            () -> AcpAgent.loadOrCreate(
                "agent:mtls.policy@localhost:9902",
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("agent-mtls"))
                    .setEndpoint("https://localhost:9902/acp/inbox")
                    .setMtlsEnabled(true)
            )
        );
        org.junit.jupiter.api.Assertions.assertTrue(exc.getMessage().contains("certFile"));
    }

    @Test
    void acceptsMtlsWhenCertificateMaterialIsConfigured(@TempDir Path tempDir) {
        Path caPath = resourcePath("tls/test-ca.pem");
        Path certPath = resourcePath("tls/test-client-cert.pem");
        Path keyPath = resourcePath("tls/test-client-key.pem");
        assertDoesNotThrow(() ->
            AcpAgent.loadOrCreate(
                "agent:mtls.policy.ok@localhost:9903",
                new AcpAgentOptions()
                    .setStorageDir(tempDir.resolve("agent-mtls-ok"))
                    .setEndpoint("https://localhost:9903/acp/inbox")
                    .setMtlsEnabled(true)
                    .setCaFile(caPath.toString())
                    .setCertFile(certPath.toString())
                    .setKeyFile(keyPath.toString())
            )
        );
    }

    private static Path resourcePath(String resource) {
        try {
            return Path.of(
                AcpAgentHttpsPolicyTest.class.getClassLoader().getResource(resource).toURI()
            );
        } catch (Exception exc) {
            throw new IllegalStateException("Missing test resource: " + resource, exc);
        }
    }
}
