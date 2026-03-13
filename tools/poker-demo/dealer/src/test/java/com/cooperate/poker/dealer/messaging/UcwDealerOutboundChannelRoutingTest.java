package com.cooperate.poker.dealer.messaging;

import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.RoundType;
import com.cooperate.poker.common.protocol.ActionAppliedMessage;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.common.protocol.HoleCardsMessage;
import com.cooperate.poker.dealer.config.DealerProperties;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

class UcwDealerOutboundChannelRoutingTest {

  private final ObjectMapper objectMapper = JsonMapper.builder().findAndAddModules().build();
  private final List<CapturedRequest> capturedRequests = new CopyOnWriteArrayList<>();
  private HttpServer server;

  @BeforeEach
  void setUp() throws Exception {
    server = HttpServer.create(new InetSocketAddress(0), 0);
    server.createContext("/", this::handleRequest);
    server.start();
  }

  @AfterEach
  void tearDown() {
    if (server != null) {
      server.stop(0);
    }
    capturedRequests.clear();
  }

  @Test
  void sendHoleCardsUsesTargetedRecipient() throws Exception {
    DealerProperties properties = baseProperties();
    DealerProperties.PlayerUcwIdentity player1 = new DealerProperties.PlayerUcwIdentity();
    player1.setParticipantUrn("urn:co-operator:entity:000101");
    properties.getPlayerUcw().put("Player-1", player1);

    UcwDealerOutboundChannel channel = new UcwDealerOutboundChannel(properties);
    setCurrentUcw(channel, UUID.randomUUID());

    HoleCardsMessage holeCards = new HoleCardsMessage(
        MessageType.HOLE_CARDS,
        "table-1",
        "Player-1",
        List.of("As", "Kd")
    );

    channel.sendHoleCards("Player-1", holeCards);

    CapturedRequest outbound = singleMessageRequest();
    JsonNode requestJson = objectMapper.readTree(outbound.body());
    assertThat(requestJson.path("payload").path("recipientParticipantUrn").asText())
        .isEqualTo("urn:co-operator:entity:000101");
  }

  @Test
  void requestActionTargetsActingPlayerOnly() throws Exception {
    DealerProperties properties = baseProperties();
    properties.setActionTimeoutMillis(250);
    properties.setUcwPollIntervalMillis(200);
    DealerProperties.PlayerUcwIdentity player2 = new DealerProperties.PlayerUcwIdentity();
    player2.setParticipantUrn("urn:co-operator:entity:000102");
    properties.getPlayerUcw().put("Player-2", player2);

    UcwDealerOutboundChannel channel = new UcwDealerOutboundChannel(properties);
    setCurrentUcw(channel, UUID.randomUUID());

    ActionRequestMessage actionRequest = new ActionRequestMessage(
        MessageType.ACTION_REQUEST,
        "table-1",
        3,
        RoundType.TURN,
        "Player-2",
        List.of("Ah", "Qs"),
        List.of("2c", "7d", "Jc", "Th"),
        120,
        20,
        20,
        380,
        20,
        List.of(ActionType.FOLD, ActionType.CALL, ActionType.RAISE)
    );

    var response = channel.requestAction("Player-2", actionRequest);
    assertThat(response).isNull();

    CapturedRequest outbound = singleMessageRequest();
    JsonNode requestJson = objectMapper.readTree(outbound.body());
    assertThat(requestJson.path("payload").path("recipientParticipantUrn").asText())
        .isEqualTo("urn:co-operator:entity:000102");
  }

  @Test
  void broadcastActionAppliedOmitsRecipientForFanout() throws Exception {
    DealerProperties properties = baseProperties();
    UcwDealerOutboundChannel channel = new UcwDealerOutboundChannel(properties);
    setCurrentUcw(channel, UUID.randomUUID());

    ActionAppliedMessage applied = new ActionAppliedMessage(
        MessageType.ACTION_APPLIED,
        "table-1",
        5,
        RoundType.RIVER,
        "Player-3",
        new PlayerAction(ActionType.BET, 40, null),
        240,
        160,
        40
    );

    channel.broadcastActionApplied(applied);

    CapturedRequest outbound = singleMessageRequest();
    JsonNode requestJson = objectMapper.readTree(outbound.body());
    JsonNode recipientNode = requestJson.path("payload").path("recipientParticipantUrn");
    assertThat(recipientNode.isMissingNode() || recipientNode.isNull() || recipientNode.asText("").isBlank()).isTrue();
  }

  private DealerProperties baseProperties() {
    DealerProperties properties = new DealerProperties();
    properties.setCoordinatorBaseUrl("http://localhost:" + server.getAddress().getPort());
    properties.setInsecureTls(false);
    properties.setBusinessProfile("co-operate:poker");
    properties.setUserUrn("urn:cooperate:dealer:test");
    properties.setTableId("table-1");
    properties.setCorrelationIdPrefix("test");
    properties.setUcwPollIntervalMillis(200);
    properties.setActionTimeoutMillis(500);
    return properties;
  }

  @SuppressWarnings("unchecked")
  private void setCurrentUcw(UcwDealerOutboundChannel channel, UUID ucwId) {
    AtomicReference<UUID> current = (AtomicReference<UUID>) ReflectionTestUtils.getField(channel, "ucwId");
    assertThat(current).isNotNull();
    current.set(ucwId);
  }

  private CapturedRequest singleMessageRequest() {
    List<CapturedRequest> messageRequests = new ArrayList<>();
    for (CapturedRequest request : capturedRequests) {
      if ("POST".equals(request.method()) && request.path().contains("/api/v1/ucws/") && request.path().endsWith("/messages")) {
        messageRequests.add(request);
      }
    }
    assertThat(messageRequests).hasSize(1);
    return messageRequests.getFirst();
  }

  private void handleRequest(HttpExchange exchange) throws IOException {
    String method = exchange.getRequestMethod();
    String path = exchange.getRequestURI().getPath();
    String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
    capturedRequests.add(new CapturedRequest(method, path, body));

    if ("POST".equals(method) && path.matches("^/api/v1/ucws/[^/]+/messages$")) {
      writeJson(exchange, 200, "{\"metadata\":{\"correlationId\":\"test\"},\"data\":{\"status\":\"ACCEPTED\"}}");
      return;
    }
    if ("GET".equals(method) && path.matches("^/api/v1/ucws/[^/]+$")) {
      writeJson(exchange, 200, "{\"ucw\":{\"status\":\"ACTIVE\",\"businessProfile\":\"co-operate:poker\",\"participants\":[]},\"inboundMessages\":[]}");
      return;
    }
    writeJson(exchange, 404, "{\"error\":\"not_found\"}");
  }

  private void writeJson(HttpExchange exchange, int status, String json) throws IOException {
    byte[] payload = json.getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set("Content-Type", "application/json");
    exchange.sendResponseHeaders(status, payload.length);
    exchange.getResponseBody().write(payload);
    exchange.close();
  }

  private record CapturedRequest(String method, String path, String body) {
  }
}
