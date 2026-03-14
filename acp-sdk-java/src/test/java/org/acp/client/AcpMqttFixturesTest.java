package org.acp.client;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AcpMqttFixturesTest {
    private static final Path VECTORS_DIR = Paths.get("..", "tests", "vectors", "mqtt").normalize();

    private static final List<String> REQUIRED_FIXTURES = List.of(
        "python_to_python_send.json",
        "java_to_python_send.json",
        "python_to_java_send.json",
        "multi_recipient_send_B.json",
        "multi_recipient_send_C.json",
        "multi_recipient_send_D.json",
        "duplicate_delivery_case.json",
        "ack_example.json",
        "fail_example.json"
    );

    private static final List<String> STANDARD_MESSAGE_FIXTURES = List.of(
        "python_to_python_send.json",
        "java_to_python_send.json",
        "python_to_java_send.json",
        "multi_recipient_send_B.json",
        "multi_recipient_send_C.json",
        "multi_recipient_send_D.json",
        "ack_example.json",
        "fail_example.json"
    );

    @Test
    void requiredMqttFixtureFilesExist() {
        for (String fixture : REQUIRED_FIXTURES) {
            assertTrue(Files.isRegularFile(VECTORS_DIR.resolve(fixture)));
        }
    }

    @Test
    void standardFixturesMatchTopicAndMetadataConventions() {
        for (String fixtureName : STANDARD_MESSAGE_FIXTURES) {
            Map<String, Object> fixture = loadFixture(fixtureName);
            Map<String, Object> body = asMap(fixture.get("serialized_body"));
            AcpMessage.fromMap(body);

            Map<String, Object> envelope = asMap(body.get("envelope"));
            List<String> recipients = asStringList(envelope.get("recipients"));
            assertEquals(1, recipients.size());
            String recipient = recipients.get(0);

            Map<String, Object> transport = asMap(fixture.get("transport_metadata"));
            assertEquals(MqttTransportClient.topicForAgent(recipient), asString(transport.get("topic")));
            assertEquals(1, asInt(transport.get("qos"), 1));
            assertEquals(
                MqttTransportClient.metadataProperties(body),
                asStringMap(transport.get("user_properties"))
            );
        }
    }

    @Test
    void duplicateFixtureUsesSameMessageId() {
        Map<String, Object> fixture = loadFixture("duplicate_delivery_case.json");
        Map<String, Object> original = asMap(fixture.get("original_message"));
        Map<String, Object> duplicate = asMap(fixture.get("duplicate_message"));

        Map<String, Object> originalBody = asMap(original.get("serialized_body"));
        Map<String, Object> duplicateBody = asMap(duplicate.get("serialized_body"));
        AcpMessage.fromMap(originalBody);
        AcpMessage.fromMap(duplicateBody);

        String originalMessageId = asString(asMap(originalBody.get("envelope")).get("message_id"));
        String duplicateMessageId = asString(asMap(duplicateBody.get("envelope")).get("message_id"));
        assertEquals(originalMessageId, duplicateMessageId);
    }

    private static Map<String, Object> loadFixture(String name) {
        try {
            return JsonSupport.mapFromJson(Files.readString(VECTORS_DIR.resolve(name)));
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to load MQTT fixture " + name, exc);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return Map.of();
    }

    private static List<String> asStringList(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream()
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .toList();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, String> asStringMap(Object value) {
        if (!(value instanceof Map<?, ?> raw)) {
            return Map.of();
        }
        Map<String, String> typed = (Map<String, String>) raw;
        return typed;
    }

    private static int asInt(Object value, int fallback) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value instanceof String str) {
            try {
                return Integer.parseInt(str);
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
        return fallback;
    }

    private static String asString(Object value) {
        return value instanceof String str ? str : null;
    }
}
