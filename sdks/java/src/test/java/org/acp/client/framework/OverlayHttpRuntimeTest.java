package org.acp.client.framework;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.acp.client.AcpAgent;
import org.acp.client.AcpAgentOptions;
import org.acp.client.AcpConstants;
import org.acp.client.AgentIdentity;
import org.acp.client.DeliveryMode;
import org.acp.client.DeliveryOutcome;
import org.acp.client.DeliveryState;
import org.acp.client.Envelope;
import org.acp.client.JsonSupport;
import org.acp.client.MessageClass;
import org.acp.client.ProtectedPayload;
import org.acp.client.CryptoSupport;
import org.acp.client.AcpMessage;
import org.acp.client.InboundResult;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OverlayHttpRuntimeTest {
    @Test
    void handlesInboundAcpMessageAndInvalidPayload(@TempDir Path tempDir) {
        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.framework@localhost:9440",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9440/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
        );
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.framework@localhost:9441",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9441/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
        );
        OverlayHttpRuntime runtime = new OverlayHttpRuntime(
            receiver,
            "http://localhost:9441",
            payload -> Map.of("accepted", true, "echo", payload)
        );

        AgentIdentity senderIdentity = AgentIdentity.create(sender.getAgentId());
        Map<String, Object> senderIdentityDocument = senderIdentity.buildIdentityDocument(
            "http://localhost:9440/acp/inbox",
            List.of(),
            "self_asserted",
            Map.of("agent_id", sender.getAgentId()),
            365
        );
        String receiverPublicKey = asString(
            asMap(asMap(receiver.getIdentityDocument().get("keys")).get("encryption")).get("public_key")
        );
        Envelope envelope = Envelope.build(
            sender.getAgentId(),
            List.of(receiver.getAgentId()),
            MessageClass.SEND,
            "overlay:runtime:inbound",
            120,
            "op-overlay-runtime-inbound",
            null,
            null,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        Map<String, Object> payload = Map.of("kind", "runtime-inbound");
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
        Map<String, Object> message = new AcpMessage(envelope, protectedPayload, senderIdentityDocument).toMap();

        OverlayHttpRuntime.HttpOverlayResponse response = runtime.handleMessageBody(message);
        assertEquals(200, response.statusCode());
        assertEquals("acp", asString(response.body().get("mode")));
        assertEquals("ACKNOWLEDGED", asString(response.body().get("state")));
        assertTrue(response.body().get("response_message") instanceof Map<?, ?>);

        OverlayHttpRuntime.HttpOverlayResponse invalid = runtime.handleMessageBody(List.of("invalid"));
        assertEquals(400, invalid.statusCode());
        assertEquals("FAILED", asString(invalid.body().get("state")));
        assertEquals("POLICY_REJECTED", asString(invalid.body().get("reason_code")));

        OverlayHttpRuntime.HttpOverlayResponse staticResponse = OverlayHttpRuntime.handle(
            message,
            inboundPayload -> Map.of("accepted", true, "echo", inboundPayload),
            new OverlayHttpRuntime.OverlayConfig(receiver, "http://localhost:9441", null)
        );
        assertEquals(200, staticResponse.statusCode());
        assertEquals("acp", asString(staticResponse.body().get("mode")));
        assertEquals("public, max-age=300", runtime.wellKnownHeaders().get("Cache-Control"));
    }

    @Test
    void outboundSendBootstrapsWellKnown(@TempDir Path tempDir) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();

        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.framework@localhost:9450",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9450/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
        );
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.framework@localhost:" + port,
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:" + port + "/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
        );
        OverlayHttpRuntime runtime = new OverlayHttpRuntime(
            sender,
            "http://localhost:9450",
            payload -> Map.of("accepted", true, "echo", payload)
        );

        Map<String, Object> wellKnown = receiver.buildWellKnownDocument("http://localhost:" + port);
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, wellKnown));
        server.createContext(
            "/api/v1/acp/identity",
            exchange -> writeJson(exchange, Map.of("identity_document", receiver.getIdentityDocument()))
        );
        server.createContext("/acp/inbox", exchange -> {
            Map<String, Object> rawMessage = JsonSupport.mapFromJson(
                new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)
            );
            InboundResult inbound = receiver.receive(rawMessage, (payload, env) -> Map.of("accepted", true));
            Map<String, Object> responseBody = new LinkedHashMap<>();
            responseBody.put("response_message", inbound.getResponseMessage());
            writeJson(exchange, responseBody);
        });
        server.start();

        try {
            Map<String, Object> response = runtime.sendAcp(
                "http://localhost:" + port,
                Map.of("kind", "runtime-outbound"),
                null,
                "overlay:runtime:outbound",
                DeliveryMode.AUTO,
                120
            );
            @SuppressWarnings("unchecked")
            Map<String, Object> target = (Map<String, Object>) response.get("target");
            assertEquals(receiver.getAgentId(), asString(target.get("agent_id")));
            assertEquals("http://localhost:" + port + "/.well-known/acp", asString(target.get("well_known_url")));

            @SuppressWarnings("unchecked")
            Map<String, Object> sendResult = (Map<String, Object>) response.get("send_result");
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> outcomes = (List<Map<String, Object>>) sendResult.get("outcomes");
            assertEquals(1, outcomes.size());
            DeliveryOutcome outcome = JsonSupport.convert(outcomes.get(0), DeliveryOutcome.class);
            assertEquals(DeliveryState.ACKNOWLEDGED, outcome.getState());
        } finally {
            server.stop(0);
        }
    }

    private static void writeJson(HttpExchange exchange, Map<String, Object> payload) throws IOException {
        byte[] body = JsonSupport.toJson(payload).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        } finally {
            exchange.close();
        }
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
