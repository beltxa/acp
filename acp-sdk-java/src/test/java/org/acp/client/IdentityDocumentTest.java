package org.acp.client;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IdentityDocumentTest {
    @Test
    void identityDocumentSignatureVerification() {
        AgentIdentity identity = AgentIdentity.create("agent:inventory.bot@localhost:9100");
        Map<String, Object> document = identity.buildIdentityDocument(
            "http://localhost:9100/acp/inbox",
            List.of("http://localhost:8080"),
            "domain_verified",
            Map.of("agent_id", identity.getAgentId()),
            365
        );
        assertTrue(AgentIdentity.verifyIdentityDocument(document));

        document.put("trust_profile", "self_asserted");
        assertFalse(AgentIdentity.verifyIdentityDocument(document));
    }

    @Test
    void rejectsUnknownTrustProfile() {
        AgentIdentity identity = AgentIdentity.create("agent:inventory.bot@localhost:9100");
        assertThrows(
            IllegalArgumentException.class,
            () -> identity.buildIdentityDocument(
                "http://localhost:9100/acp/inbox",
                List.of("http://localhost:8080"),
                "unsupported_profile",
                Map.of(),
                365
            )
        );
    }
}
