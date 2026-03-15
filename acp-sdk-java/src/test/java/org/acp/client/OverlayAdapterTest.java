package org.acp.client;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
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
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OverlayAdapterTest {
    @Test
    void inboundOverlayHandlesAcpAndPassthrough(@TempDir Path tempDir) {
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.overlay@localhost:9421",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:9421/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
        );

        AgentIdentity senderIdentity = AgentIdentity.create("agent:sender.overlay@localhost:9420");
        Map<String, Object> senderIdentityDocument = senderIdentity.buildIdentityDocument(
            "http://localhost:9420/acp/inbox",
            List.of(),
            "self_asserted",
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
            "overlay:inbound",
            120,
            "op-overlay-inbound",
            null,
            null,
            AcpConstants.DEFAULT_CRYPTO_SUITE
        );
        Map<String, Object> payload = Map.of("kind", "overlay-test");
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

        OverlayInboundAdapter adapter = new OverlayInboundAdapter(
            receiver,
            businessPayload -> Map.of("accepted", true),
            body -> Map.of("echo", body)
        );

        Map<String, Object> acpResult = adapter.handleRequest(message);
        assertEquals("acp", acpResult.get("mode"));
        assertEquals("ACKNOWLEDGED", asString(acpResult.get("state")));
        assertTrue(acpResult.get("response_message") instanceof Map<?, ?>);

        Map<String, Object> passthrough = adapter.handleRequest(Map.of("legacy", "payload"));
        assertEquals("passthrough", passthrough.get("mode"));
        assertTrue(passthrough.get("payload") instanceof Map<?, ?>);

        OverlayInboundAdapter strict = new OverlayInboundAdapter(
            receiver,
            businessPayload -> Map.of("accepted", true)
        );
        assertThrows(IllegalArgumentException.class, () -> strict.handleRequest(Map.of("legacy", "payload")));
    }

    @Test
    void outboundOverlayBootstrapsFromWellKnownAndSends(@TempDir Path tempDir) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();

        AcpAgent sender = AcpAgent.loadOrCreate(
            "agent:sender.overlay@localhost:9430",
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("sender"))
                .setEndpoint("http://localhost:9430/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
        );
        AcpAgent receiver = AcpAgent.loadOrCreate(
            "agent:receiver.overlay@localhost:" + port,
            new AcpAgentOptions()
                .setStorageDir(tempDir.resolve("receiver"))
                .setEndpoint("http://localhost:" + port + "/acp/inbox")
                .setAllowInsecureHttp(true)
                .setDiscoveryScheme("http")
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
            OverlayOutboundAdapter outbound = new OverlayOutboundAdapter(sender);
            OverlayOutboundAdapter.OverlaySendResult result = outbound.sendBusinessPayload(
                Map.of("kind", "overlay-outbound"),
                "http://localhost:" + port,
                null,
                "overlay:java",
                DeliveryMode.AUTO,
                120
            );
            assertNotNull(result.target());
            assertEquals(receiver.getAgentId(), result.target().agentId());
            assertEquals("http://localhost:" + port + "/.well-known/acp", result.target().wellKnownUrl());
            assertEquals(1, result.sendResult().getOutcomes().size());
            DeliveryOutcome outcome = result.sendResult().getOutcomes().get(0);
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
