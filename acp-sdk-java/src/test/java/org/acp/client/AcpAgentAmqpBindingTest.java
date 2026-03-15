package org.acp.client;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AcpAgentAmqpBindingTest {
    @Test
    void amqpRoutingConventionsUseAgentIdentifierToken() {
        String agentId = "agent:shipping.bot@companyB.com";
        assertEquals("acp.agent.shipping.bot.companyB.com", AmqpTransportClient.queueNameForAgent(agentId));
        assertEquals("agent.shipping.bot.companyB.com", AmqpTransportClient.routingKeyForAgent(agentId));
    }

    @Test
    void sendAmqpPublishesOneMessagePerRecipient(@TempDir Path tempDir) {
        FakeAmqpTransport fakeTransport = new FakeAmqpTransport();
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9400",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9400/acp/inbox")
                .setAmqpTransport(fakeTransport)
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        AcpAgent recipient1 = AcpAgent.loadOrCreate(
            "agent:recipient1.bot@localhost:9401",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("recipient1"))
                .setEndpoint("http://localhost:9401/acp/inbox")
                .setAmqpBrokerUrl("amqp://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        AcpAgent recipient2 = AcpAgent.loadOrCreate(
            "agent:recipient2.bot@localhost:9402",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("recipient2"))
                .setEndpoint("http://localhost:9402/acp/inbox")
                .setAmqpBrokerUrl("amqp://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );

        sender.registerIdentityDocument(recipient1.getIdentityDocument());
        sender.registerIdentityDocument(recipient2.getIdentityDocument());

        SendResult result = sender.send(
            List.of(recipient1.getAgentId(), recipient2.getAgentId()),
            Map.of("type", "hand_start", "hand_id", "h-1"),
            "ctx-amqp",
            MessageClass.SEND,
            300,
            null,
            null,
            DeliveryMode.AMQP
        );

        assertEquals(2, fakeTransport.published.size());
        for (FakeAmqpTransport.PublishCall call : fakeTransport.published) {
            Map<String, Object> envelope = asMap(call.message().get("envelope"));
            assertEquals(List.of(call.recipient()), envelope.get("recipients"));
            assertEquals(
                AmqpTransportClient.routingKeyForAgent(call.recipient()),
                call.routingKey()
            );
        }
        assertEquals(2, result.getMessageIds().size());
        assertTrue(result.getOutcomes().stream().allMatch(outcome -> outcome.getState() == DeliveryState.DELIVERED));
    }

    @Test
    void consumeFromAmqpAcknowledgesDuplicateDelivery(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9500",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9500/acp/inbox")
                .setAmqpBrokerUrl("amqp://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );

        FakeAmqpTransport fakeTransport = new FakeAmqpTransport();
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.bot@localhost:9501",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9501/acp/inbox")
                .setAmqpBrokerUrl("amqp://broker.local")
                .setAmqpTransport(fakeTransport)
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        receiver.registerIdentityDocument(sender.getIdentityDocument());

        String receiverPublicKey = asString(
            asMap(asMap(receiver.getIdentityDocument().get("keys")).get("encryption")).get("public_key")
        );
        AgentIdentity senderIdentity = AgentIdentity.readIdentity(tempDir.resolve("sender"), sender.getAgentId()).identity();
        Envelope envelope = Envelope.build(
            sender.getAgentId(),
            List.of(receiver.getAgentId()),
            MessageClass.SEND,
            "ctx-dup",
            60,
            "op-dup",
            null,
            null,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        Map<String, Object> payload = Map.of("type", "ping");
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
        AcpMessage message = new AcpMessage(envelope, protectedPayload, sender.getIdentityDocument());

        fakeTransport.queuedMessages.add(message.toMap());
        fakeTransport.queuedMessages.add(message.toMap());

        int consumed = receiver.consumeFromAmqp(2);
        assertEquals(2, consumed);
        assertEquals(List.of(true, true), fakeTransport.acknowledgements);
        assertEquals(2, fakeTransport.published.size());
        assertTrue(fakeTransport.published.stream().allMatch(call ->
            MessageClass.ACK.name().equals(asString(asMap(call.message().get("envelope")).get("message_class")))
        ));
    }

    @Test
    void consumeFromAmqpPublishesAckResponseToSender(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9600",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9600/acp/inbox")
                .setAmqpBrokerUrl("amqp://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );

        FakeAmqpTransport fakeTransport = new FakeAmqpTransport();
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.bot@localhost:9601",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9601/acp/inbox")
                .setAmqpBrokerUrl("amqp://broker.local")
                .setAmqpTransport(fakeTransport)
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        receiver.registerIdentityDocument(sender.getIdentityDocument());

        String receiverPublicKey = asString(
            asMap(asMap(receiver.getIdentityDocument().get("keys")).get("encryption")).get("public_key")
        );
        AgentIdentity senderIdentity = AgentIdentity.readIdentity(tempDir.resolve("sender"), sender.getAgentId()).identity();
        Envelope envelope = Envelope.build(
            sender.getAgentId(),
            List.of(receiver.getAgentId()),
            MessageClass.SEND,
            "ctx-roundtrip",
            60,
            "op-roundtrip",
            null,
            null,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        Map<String, Object> payload = Map.of("type", "ping");
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
        AcpMessage message = new AcpMessage(envelope, protectedPayload, sender.getIdentityDocument());

        fakeTransport.queuedMessages.add(message.toMap());
        int consumed = receiver.consumeFromAmqp(1);
        assertEquals(1, consumed);
        assertEquals(List.of(true), fakeTransport.acknowledgements);
        assertEquals(1, fakeTransport.published.size());
        FakeAmqpTransport.PublishCall published = fakeTransport.published.get(0);
        assertEquals(sender.getAgentId(), published.recipient());
        assertEquals(MessageClass.ACK.name(), asString(asMap(published.message().get("envelope")).get("message_class")));
        assertEquals(
            AmqpTransportClient.routingKeyForAgent(sender.getAgentId()),
            published.routingKey()
        );
    }

    @Test
    void receiveAckMessageDoesNotGenerateAckOfAck(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9700",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9700/acp/inbox")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.bot@localhost:9701",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9701/acp/inbox")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        sender.registerIdentityDocument(receiver.getIdentityDocument());

        String senderPublicKey = asString(
            asMap(asMap(sender.getIdentityDocument().get("keys")).get("encryption")).get("public_key")
        );
        AgentIdentity receiverIdentity = AgentIdentity.readIdentity(tempDir.resolve("receiver"), receiver.getAgentId()).identity();
        Envelope envelope = Envelope.build(
            receiver.getAgentId(),
            List.of(sender.getAgentId()),
            MessageClass.ACK,
            "ctx-ack",
            60,
            "op-ack",
            "op-original",
            "m-original",
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        Map<String, Object> payload = Map.of("status", "accepted", "received_message_id", "m-original");
        ProtectedPayload protectedPayload = CryptoSupport.encryptForRecipients(
            payload,
            envelope,
            Map.of(sender.getAgentId(), senderPublicKey)
        );
        protectedPayload = CryptoSupport.signProtectedPayload(
            envelope,
            protectedPayload,
            receiverIdentity.getSigningPrivateKey(),
            receiverIdentity.getSigningKid()
        );
        AcpMessage ack = new AcpMessage(envelope, protectedPayload, receiver.getIdentityDocument());

        InboundResult result = sender.receive(ack.toMap(), null);
        assertEquals(DeliveryState.ACKNOWLEDGED, result.getState());
        assertNull(result.getResponseMessage());
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

    private static final class FakeAmqpTransport extends AmqpTransportClient {
        private final List<PublishCall> published = new ArrayList<>();
        private final List<Map<String, Object>> queuedMessages = new ArrayList<>();
        private final List<Boolean> acknowledgements = new ArrayList<>();

        private FakeAmqpTransport() {
            super("amqp://broker.local", DEFAULT_EXCHANGE, DEFAULT_EXCHANGE_TYPE, 1);
        }

        @Override
        public void publish(Map<String, Object> message, String recipientAgentId, Map<String, Object> amqpService) {
            Map<String, Object> service = amqpService == null ? Map.of() : new LinkedHashMap<>(amqpService);
            String routingKey = asString(service.get("routing_key"));
            published.add(new PublishCall(recipientAgentId, routingKey, message));
        }

        @Override
        public int consume(String agentId, MessageHandler handler, Map<String, Object> amqpService, int maxMessages) {
            int consumed = 0;
            for (Map<String, Object> message : queuedMessages) {
                if (consumed >= maxMessages) {
                    break;
                }
                acknowledgements.add(handler.handle(message));
                consumed++;
            }
            return consumed;
        }

        private record PublishCall(String recipient, String routingKey, Map<String, Object> message) {
        }
    }
}
