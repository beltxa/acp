package org.acp.client;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CryptoSupportTest {
    @Test
    void encryptSignVerifyDecryptRoundtrip() {
        AgentIdentity sender = AgentIdentity.create("agent:sender@localhost:9101");
        AgentIdentity recipient = AgentIdentity.create("agent:recipient@localhost:9102");

        Envelope envelope = Envelope.build(
            sender.getAgentId(),
            List.of(recipient.getAgentId()),
            MessageClass.SEND,
            "ctx-1",
            60,
            null,
            null,
            null,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        envelope.setTenant("tenant.demo");
        assertEquals("tenant.demo", envelope.getTenant());
        Map<String, Object> payload = Map.of(
            "type", "hello",
            "data", Map.of("value", 42)
        );

        ProtectedPayload protectedPayload = CryptoSupport.encryptForRecipients(
            payload,
            envelope,
            Map.of(recipient.getAgentId(), recipient.getEncryptionPublicKey())
        );
        protectedPayload = CryptoSupport.signProtectedPayload(
            envelope,
            protectedPayload,
            sender.getSigningPrivateKey(),
            sender.getSigningKid()
        );

        assertTrue(CryptoSupport.verifyProtectedPayloadSignature(
            envelope,
            protectedPayload,
            sender.getSigningPublicKey()
        ));
        Map<String, Object> decrypted = CryptoSupport.decryptForRecipient(
            envelope,
            protectedPayload,
            recipient.getAgentId(),
            recipient.getEncryptionPrivateKey()
        );
        assertEquals(payload, decrypted);
    }
}
