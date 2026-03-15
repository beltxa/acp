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
}
