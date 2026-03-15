package org.acp.client;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DiscoveryClientWellKnownTest {
    @Test
    void resolvesIdentityFromWellKnownMetadata() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();
        String agentId = "agent:shipping.bot@localhost:" + port;
        AgentIdentity identity = AgentIdentity.create(agentId);
        Map<String, Object> identityDocument = identity.buildIdentityDocument(
            "http://localhost:" + port + "/acp/inbox",
            List.of("http://localhost:8080"),
            "domain_verified",
            Map.of("agent_id", agentId),
            365
        );
        Map<String, Object> wellKnown = Map.of(
            "agent_id", agentId,
            "identity_document", "/api/v1/acp/identity",
            "transports", Map.of("http", Map.of("endpoint", "http://localhost:" + port + "/acp/inbox")),
            "version", "1.0",
            "security_profile", "http"
        );
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, wellKnown));
        server.createContext("/api/v1/acp/identity", exchange -> writeJson(exchange, Map.of("identity_document", identityDocument)));
        server.start();

        Path cacheDir = Files.createTempDirectory("acp-discovery-wk");
        try {
            DiscoveryClient client = new DiscoveryClient(
                cacheDir.resolve("discovery_cache.json"),
                "http",
                List.of(),
                List.of(),
                5,
                true,
                false,
                null,
                false,
                null,
                null
            );
            Map<String, Object> resolved = client.resolve(agentId);
            assertEquals(agentId, resolved.get("agent_id"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void resolvesWellKnownByBaseUrl() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();
        String agentId = "agent:trading.bot@localhost:" + port;
        AgentIdentity identity = AgentIdentity.create(agentId);
        Map<String, Object> identityDocument = identity.buildIdentityDocument(
            "http://localhost:" + port + "/acp/inbox",
            List.of(),
            "domain_verified",
            Map.of("agent_id", agentId),
            365
        );
        Map<String, Object> wellKnown = Map.of(
            "agent_id", agentId,
            "identity_document", "http://localhost:" + port + "/api/v1/acp/identity",
            "transports", Map.of("http", Map.of("endpoint", "http://localhost:" + port + "/acp/inbox")),
            "version", "1.0",
            "security_profile", "http"
        );
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, wellKnown));
        server.createContext("/api/v1/acp/identity", exchange -> writeJson(exchange, Map.of("identity_document", identityDocument)));
        server.start();

        Path cacheDir = Files.createTempDirectory("acp-discovery-wk-base");
        try {
            DiscoveryClient client = new DiscoveryClient(
                cacheDir.resolve("discovery_cache.json"),
                "http",
                List.of(),
                List.of(),
                5,
                true,
                false,
                null,
                false,
                null,
                null
            );
            Map<String, Object> resolved = client.resolveWellKnown("http://localhost:" + port, agentId);
            assertEquals("http://localhost:" + port + "/.well-known/acp", resolved.get("well_known_url"));
            @SuppressWarnings("unchecked")
            Map<String, Object> resolvedWellKnown = (Map<String, Object>) resolved.get("well_known");
            assertEquals(agentId, resolvedWellKnown.get("agent_id"));
            @SuppressWarnings("unchecked")
            Map<String, Object> resolvedIdentity = (Map<String, Object>) resolved.get("identity_document");
            assertEquals(agentId, resolvedIdentity.get("agent_id"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void buildsWellKnownDocumentFromAgent() throws Exception {
        Path storageDir = Files.createTempDirectory("acp-agent-well-known");
        AcpAgentOptions options = new AcpAgentOptions()
            .setStorageDir(storageDir)
            .setEndpoint("http://localhost:9810/acp/inbox")
            .setRelayHints(List.of("http://localhost:8080"))
            .setAllowInsecureHttp(true)
            .setDiscoveryScheme("http");

        AcpAgent agent = AcpAgent.loadOrCreate("agent:demo.bot@localhost:9810", options);
        Map<String, Object> wellKnown = agent.buildWellKnownDocument("http://localhost:9810");

        assertEquals("agent:demo.bot@localhost:9810", wellKnown.get("agent_id"));
        assertEquals("http://localhost:9810/api/v1/acp/identity", wellKnown.get("identity_document"));
        @SuppressWarnings("unchecked")
        Map<String, Object> transports = (Map<String, Object>) wellKnown.get("transports");
        assertTrue(transports.containsKey("http"));
    }

    @Test
    void rejectsWellKnownWithInvalidVersion() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();
        Map<String, Object> malformed = Map.of(
            "agent_id", "agent:demo.bot@localhost:" + port,
            "identity_document", "/api/v1/acp/identity",
            "transports", Map.of("http", Map.of("endpoint", "http://localhost:" + port + "/acp/inbox")),
            "version", "2.0"
        );
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, malformed));
        server.start();

        Path cacheDir = Files.createTempDirectory("acp-discovery-wk-invalid-version");
        try {
            DiscoveryClient client = new DiscoveryClient(
                cacheDir.resolve("discovery_cache.json"),
                "http",
                List.of(),
                List.of(),
                5,
                true,
                false,
                null,
                false,
                null,
                null
            );
            assertThrows(
                IllegalStateException.class,
                () -> client.resolveWellKnown("http://localhost:" + port, "agent:demo.bot@localhost:" + port)
            );
        } finally {
            server.stop(0);
        }
    }

    @Test
    void rejectsWellKnownWithNonStringIdentityReference() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();
        Map<String, Object> malformed = Map.of(
            "agent_id", "agent:demo.bot@localhost:" + port,
            "identity_document", Map.of("agent_id", "agent:demo.bot@localhost:" + port),
            "transports", Map.of("http", Map.of("endpoint", "http://localhost:" + port + "/acp/inbox")),
            "version", "1.0"
        );
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, malformed));
        server.start();

        Path cacheDir = Files.createTempDirectory("acp-discovery-wk-invalid-identity-reference");
        try {
            DiscoveryClient client = new DiscoveryClient(
                cacheDir.resolve("discovery_cache.json"),
                "http",
                List.of(),
                List.of(),
                5,
                true,
                false,
                null,
                false,
                null,
                null
            );
            assertThrows(
                IllegalStateException.class,
                () -> client.resolveWellKnown("http://localhost:" + port, "agent:demo.bot@localhost:" + port)
            );
        } finally {
            server.stop(0);
        }
    }

    @Test
    void rejectsWellKnownWithInvalidTransportEndpointUrl() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();
        Map<String, Object> malformed = Map.of(
            "agent_id", "agent:demo.bot@localhost:" + port,
            "identity_document", "/api/v1/acp/identity",
            "transports", Map.of("http", Map.of("endpoint", "https:///acp/inbox")),
            "version", "1.0"
        );
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, malformed));
        server.start();

        Path cacheDir = Files.createTempDirectory("acp-discovery-wk-invalid-endpoint");
        try {
            DiscoveryClient client = new DiscoveryClient(
                cacheDir.resolve("discovery_cache.json"),
                "http",
                List.of(),
                List.of(),
                5,
                true,
                false,
                null,
                false,
                null,
                null
            );
            assertThrows(
                IllegalStateException.class,
                () -> client.resolveWellKnown("http://localhost:" + port, "agent:demo.bot@localhost:" + port)
            );
        } finally {
            server.stop(0);
        }
    }

    @Test
    void rejectsWellKnownWithUnsupportedSecurityProfile() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        int port = server.getAddress().getPort();
        Map<String, Object> malformed = Map.of(
            "agent_id", "agent:demo.bot@localhost:" + port,
            "identity_document", "/api/v1/acp/identity",
            "transports", Map.of("http", Map.of("endpoint", "http://localhost:" + port + "/acp/inbox")),
            "version", "1.0",
            "security_profile", "invalid-profile"
        );
        server.createContext("/.well-known/acp", exchange -> writeJson(exchange, malformed));
        server.start();

        Path cacheDir = Files.createTempDirectory("acp-discovery-wk-invalid-profile");
        try {
            DiscoveryClient client = new DiscoveryClient(
                cacheDir.resolve("discovery_cache.json"),
                "http",
                List.of(),
                List.of(),
                5,
                true,
                false,
                null,
                false,
                null,
                null
            );
            assertThrows(
                IllegalStateException.class,
                () -> client.resolveWellKnown("http://localhost:" + port, "agent:demo.bot@localhost:" + port)
            );
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
}
