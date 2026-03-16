package org.acp.client;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class AcpAgentInboundTest {
    @Test
    void receiveAcknowledgesAndDeduplicates(@TempDir Path tempDir) {
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.bot@localhost:9301",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9301/acp/inbox")
                .setRelayUrl("http://localhost:8080")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
                .setTrustProfile("domain_verified")
        );

        AgentIdentity senderIdentity = AgentIdentity.create("agent:sender.bot@localhost:9300");
        Map<String, Object> senderIdentityDocument = senderIdentity.buildIdentityDocument(
            "http://localhost:9300/acp/inbox",
            List.of("http://localhost:8080"),
            "domain_verified",
            Map.of("agent_id", senderIdentity.getAgentId()),
            365
        );

        String receiverPublicKey = asString(
            asMap(asMap(receiver.getIdentityDocument().get("keys")).get("encryption")).get("public_key")
        );
        Envelope envelope = Envelope.build(
            senderIdentity.getAgentId(),
            List.of(receiver.getAgentId()),
            MessageClass.SEND,
            "ctx-1",
            60,
            null,
            null,
            null,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );

        Map<String, Object> payload = Map.of("type", "ping", "hand_id", "123");
        ProtectedPayload protectedPayload = CryptoSupport.encryptForRecipients(
            payload,
            envelope,
            Map.of(receiver.getAgentId(), receiverPublicKey)
        );
        protectedPayload = CryptoSupport.signProtectedPayload(
            envelope,
            protectedPayload,
            senderIdentity.getSigningPrivateKey(),
            senderIdentity.getSigningKid()
        );
        AcpMessage message = new AcpMessage(envelope, protectedPayload, senderIdentityDocument);

        InboundResult first = receiver.receive(message.toMap(), null);
        assertEquals(DeliveryState.ACKNOWLEDGED, first.getState());
        assertEquals(payload, first.getDecryptedPayload());
        assertNotNull(first.getResponseMessage());

        InboundResult second = receiver.receive(message.toMap(), null);
        assertEquals(DeliveryState.ACKNOWLEDGED, second.getState());
        assertNotNull(second.getResponseMessage());
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
}
