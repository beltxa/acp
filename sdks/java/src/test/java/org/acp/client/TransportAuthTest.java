package org.acp.client;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class TransportAuthTest {
    @Test
    void buildsBearerAuthHeaders() {
        AuthConfig auth = TransportAuth.parseAuthConfig(
            Map.of("type", "bearer", "parameters", Map.of("token", "demo-token"))
        );
        Map<String, String> headers = TransportAuth.httpAuthHeaders(auth);
        assertEquals("Bearer demo-token", headers.get("Authorization"));
    }

    @Test
    void embedsAuthInAmqpAndMqttServiceHints() {
        Map<String, Object> amqpHint = AmqpTransportClient.buildServiceHint(
            "agent:sender@demo",
            "amqps://broker.local",
            "acp.exchange",
            Map.of(
                "type",
                "username_password",
                "parameters",
                Map.of("username", "agentA", "password", "secret")
            )
        );
        assertEquals("username_password", asMap(amqpHint.get("auth")).get("type"));

        Map<String, Object> mqttHint = MqttTransportClient.buildServiceHint(
            "agent:sender@demo",
            "mqtts://broker.local:8883",
            null,
            1,
            "acp/agent",
            Map.of(
                "type",
                "username_password",
                "parameters",
                Map.of("username", "agentA", "password", "secret")
            )
        );
        assertEquals("username_password", asMap(mqttHint.get("auth")).get("type"));
    }

    @Test
    void parsesAndSerializesTransportAuthFromAgentOptions() {
        AcpAgentOptions options = new AcpAgentOptions()
            .setDirectTransportAuth(Map.of("type", "bearer", "parameters", Map.of("token", "direct-token")))
            .setRelayTransportAuth(Map.of("type", "bearer", "parameters", Map.of("token", "relay-token")))
            .setAmqpAuth(Map.of(
                "type",
                "username_password",
                "parameters",
                Map.of("username", "agentA", "password", "secret")
            ))
            .setMqttAuth(Map.of(
                "type",
                "username_password",
                "parameters",
                Map.of("username", "agentA", "password", "secret")
            ));
        Map<String, Object> exported = options.toConfigMap();
        assertNotNull(exported.get("direct_transport_auth"));
        assertNotNull(exported.get("relay_transport_auth"));
        assertNotNull(exported.get("amqp_auth"));
        assertNotNull(exported.get("mqtt_auth"));

        AcpAgentOptions parsed = AcpAgentOptions.fromConfigMap(exported);
        assertEquals("bearer", asMap(parsed.getDirectTransportAuth()).get("type"));
        assertEquals("bearer", asMap(parsed.getRelayTransportAuth()).get("type"));
        assertEquals("username_password", asMap(parsed.getAmqpAuth()).get("type"));
        assertEquals("username_password", asMap(parsed.getMqttAuth()).get("type"));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return (Map<String, Object>) value;
    }
}
