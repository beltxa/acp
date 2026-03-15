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

class AcpAgentMqttBindingTest {
    @Test
    void mqttTopicAndIdentifierNormalizationIsStable() {
        String agentId = "agent:Shipping.Bot@CompanyB.com";
        assertEquals("shipping.bot.companyb.com", MqttTransportClient.agentIdentifierToken(agentId));
        assertEquals("acp/agent/shipping.bot.companyb.com", MqttTransportClient.topicForAgent(agentId));
    }

    @Test
    void sendMqttPublishesOneMessagePerRecipient(@TempDir Path tempDir) {
        FakeMqttTransport fakeTransport = new FakeMqttTransport();
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9800",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9800/acp/inbox")
                .setMqttTransport(fakeTransport)
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        AcpAgent recipient1 = AcpAgent.loadOrCreate(
            "agent:recipient1.bot@localhost:9801",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("recipient1"))
                .setEndpoint("http://localhost:9801/acp/inbox")
                .setMqttBrokerUrl("mqtt://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        AcpAgent recipient2 = AcpAgent.loadOrCreate(
            "agent:recipient2.bot@localhost:9802",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("recipient2"))
                .setEndpoint("http://localhost:9802/acp/inbox")
                .setMqttBrokerUrl("mqtt://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );

        sender.registerIdentityDocument(recipient1.getIdentityDocument());
        sender.registerIdentityDocument(recipient2.getIdentityDocument());

        SendResult result = sender.send(
            List.of(recipient1.getAgentId(), recipient2.getAgentId()),
            Map.of("type", "table_state", "table_id", "t-1"),
            "ctx-mqtt",
            MessageClass.SEND,
            300,
            null,
            null,
            DeliveryMode.MQTT
        );

        assertEquals(2, fakeTransport.published.size());
        for (FakeMqttTransport.PublishCall call : fakeTransport.published) {
            Map<String, Object> envelope = asMap(call.message().get("envelope"));
            assertEquals(List.of(call.recipient()), envelope.get("recipients"));
            List<Map<String, Object>> wrappedKeys = asMapList(
                asMap(call.message().get("protected")).get("wrapped_content_keys")
            );
            assertEquals(1, wrappedKeys.size());
            assertEquals(call.recipient(), asString(wrappedKeys.get(0).get("recipient")));
            assertEquals(MqttTransportClient.topicForAgent(call.recipient()), call.topic());
        }
        assertEquals(2, result.getMessageIds().size());
        assertTrue(result.getOutcomes().stream().allMatch(outcome -> outcome.getState() == DeliveryState.DELIVERED));
    }

    @Test
    void consumeFromMqttAcknowledgesDuplicateDelivery(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9810",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9810/acp/inbox")
                .setMqttBrokerUrl("mqtt://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );

        FakeMqttTransport fakeTransport = new FakeMqttTransport();
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.bot@localhost:9811",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9811/acp/inbox")
                .setMqttBrokerUrl("mqtt://broker.local")
                .setMqttTransport(fakeTransport)
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        receiver.registerIdentityDocument(sender.getIdentityDocument());

        AcpMessage message = buildSignedMessage(
            tempDir.resolve("sender"),
            sender,
            receiver,
            MessageClass.SEND,
            Map.of("type", "ping"),
            "ctx-mqtt-dup",
            "op-mqtt-dup",
            null,
            null
        );
        fakeTransport.queuedMessages.add(message.toMap());
        fakeTransport.queuedMessages.add(message.toMap());

        int consumed = receiver.consumeFromMqtt(2);
        assertEquals(2, consumed);
        assertEquals(List.of(true, true), fakeTransport.acknowledgements);
        assertEquals(2, fakeTransport.published.size());
        assertTrue(fakeTransport.published.stream().allMatch(call ->
            MessageClass.ACK.name().equals(asString(asMap(call.message().get("envelope")).get("message_class")))
        ));
    }

    @Test
    void consumeFromMqttPublishesAckResponseToSender(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9820",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9820/acp/inbox")
                .setMqttBrokerUrl("mqtt://broker.local")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );

        FakeMqttTransport fakeTransport = new FakeMqttTransport();
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.bot@localhost:9821",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9821/acp/inbox")
                .setMqttBrokerUrl("mqtt://broker.local")
                .setMqttTransport(fakeTransport)
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        receiver.registerIdentityDocument(sender.getIdentityDocument());

        AcpMessage message = buildSignedMessage(
            tempDir.resolve("sender"),
            sender,
            receiver,
            MessageClass.SEND,
            Map.of("type", "ping"),
            "ctx-mqtt-roundtrip",
            "op-mqtt-roundtrip",
            null,
            null
        );
        fakeTransport.queuedMessages.add(message.toMap());

        int consumed = receiver.consumeFromMqtt(1);
        assertEquals(1, consumed);
        assertEquals(List.of(true), fakeTransport.acknowledgements);
        assertEquals(1, fakeTransport.published.size());
        FakeMqttTransport.PublishCall published = fakeTransport.published.get(0);
        assertEquals(sender.getAgentId(), published.recipient());
        assertEquals(MessageClass.ACK.name(), asString(asMap(published.message().get("envelope")).get("message_class")));
        assertEquals(MqttTransportClient.topicForAgent(sender.getAgentId()), published.topic());
    }

    @Test
    void receiveAckAndFailMessagesDoNotGenerateResponseLoops(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.bot@localhost:9830",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9830/acp/inbox")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        AcpAgent responder = AcpAgent.loadOrCreate(
            "agent:responder.bot@localhost:9831",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("responder"))
                .setEndpoint("http://localhost:9831/acp/inbox")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        sender.registerIdentityDocument(responder.getIdentityDocument());

        AcpMessage ack = buildSignedMessage(
            tempDir.resolve("responder"),
            responder,
            sender,
            MessageClass.ACK,
            Map.of("status", "accepted", "received_message_id", "m-original"),
            "ctx-ack",
            "op-ack",
            "op-original",
            "m-original"
        );
        InboundResult ackResult = sender.receive(ack.toMap(), null);
        assertEquals(DeliveryState.ACKNOWLEDGED, ackResult.getState());
        assertNull(ackResult.getResponseMessage());

        AcpMessage fail = buildSignedMessage(
            tempDir.resolve("responder"),
            responder,
            sender,
            MessageClass.FAIL,
            Map.of("reason_code", "POLICY_REJECTED", "detail", "failed"),
            "ctx-fail",
            "op-fail",
            "op-original",
            "m-original"
        );
        InboundResult failResult = sender.receive(fail.toMap(), null);
        assertEquals(DeliveryState.ACKNOWLEDGED, failResult.getState());
        assertNull(failResult.getResponseMessage());
    }

    private static AcpMessage buildSignedMessage(
        Path senderStorageDir,
        AcpAgent sender,
        AcpAgent recipient,
        MessageClass messageClass,
        Map<String, Object> payload,
        String contextId,
        String operationId,
        String correlationId,
        String inReplyTo
    ) {
        String recipientPublicKey = asString(
            asMap(asMap(recipient.getIdentityDocument().get("keys")).get("encryption")).get("public_key")
        );
        AgentIdentity senderIdentity = AgentIdentity.readIdentity(senderStorageDir, sender.getAgentId()).identity();
        Envelope envelope = Envelope.build(
            sender.getAgentId(),
            List.of(recipient.getAgentId()),
            messageClass,
            contextId,
            60,
            operationId,
            correlationId,
            inReplyTo,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        ProtectedPayload protectedPayload = CryptoSupport.encryptForRecipients(
            payload,
            envelope,
            Map.of(recipient.getAgentId(), recipientPublicKey)
        );
        protectedPayload = CryptoSupport.signProtectedPayload(
            envelope,
            protectedPayload,
            senderIdentity.getSigningPrivateKey(),
            senderIdentity.getSigningKid()
        );
        return new AcpMessage(envelope, protectedPayload, sender.getIdentityDocument());
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return Map.of();
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> asMapList(Object value) {
        if (value instanceof List<?> raw) {
            return (List<Map<String, Object>>) raw;
        }
        return List.of();
    }

    private static String asString(Object value) {
        return value instanceof String str ? str : null;
    }

    private static final class FakeMqttTransport extends MqttTransportClient {
        private final List<PublishCall> published = new ArrayList<>();
        private final List<Map<String, Object>> queuedMessages = new ArrayList<>();
        private final List<Boolean> acknowledgements = new ArrayList<>();

        private FakeMqttTransport() {
            super("mqtt://broker.local", DEFAULT_QOS, DEFAULT_TOPIC_PREFIX, 1, 1);
        }

        @Override
        public void publish(Map<String, Object> message, String recipientAgentId, Map<String, Object> mqttService) {
            Map<String, Object> service = mqttService == null ? Map.of() : new LinkedHashMap<>(mqttService);
            String topic = asString(service.get("topic"));
            published.add(new PublishCall(recipientAgentId, topic, message));
        }

        @Override
        public int consume(String agentId, MessageHandler handler, Map<String, Object> mqttService, int maxMessages) {
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

        private record PublishCall(String recipient, String topic, Map<String, Object> message) {
        }
    }
}
