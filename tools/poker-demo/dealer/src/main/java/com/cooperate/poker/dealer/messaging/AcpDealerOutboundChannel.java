package com.cooperate.poker.dealer.messaging;

import com.cooperate.poker.common.messaging.DealerOutboundChannel;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.protocol.ActionAppliedMessage;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.common.protocol.ActionResponseMessage;
import com.cooperate.poker.common.protocol.CommunityCardsUpdatedMessage;
import com.cooperate.poker.common.protocol.GameFinishedMessage;
import com.cooperate.poker.common.protocol.HandResultMessage;
import com.cooperate.poker.common.protocol.HandStartMessage;
import com.cooperate.poker.common.protocol.HoleCardsMessage;
import com.cooperate.poker.common.protocol.InvitationMessage;
import com.cooperate.poker.common.protocol.JoinTableMessage;
import com.cooperate.poker.common.protocol.PokerPayloadCodec;
import com.cooperate.poker.common.protocol.PokerPayloadEvent;
import com.cooperate.poker.common.protocol.PlayerEliminatedMessage;
import com.cooperate.poker.dealer.config.DealerProperties;
import org.acp.client.AcpAgent;
import org.acp.client.AcpAgentOptions;
import org.acp.client.DeliveryMode;
import org.acp.client.DeliveryOutcome;
import org.acp.client.DeliveryState;
import org.acp.client.InboundResult;
import org.acp.client.SendResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

@Component
@ConditionalOnProperty(name = "poker.dealer.transport-mode", havingValue = "ACP")
public class AcpDealerOutboundChannel implements DealerOutboundChannel {
  private static final Logger log = LoggerFactory.getLogger(AcpDealerOutboundChannel.class);

  private final DealerProperties properties;
  private final ObjectMapper objectMapper;
  private final PokerPayloadCodec payloadCodec;
  private final AcpAgent agent;
  private final DeliveryMode deliveryMode;
  private final AtomicInteger outboundSequence = new AtomicInteger(0);
  private final ConcurrentMap<String, Deque<JoinTableMessage>> joinResponses = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, Deque<ActionResponseMessage>> actionResponses = new ConcurrentHashMap<>();

  public AcpDealerOutboundChannel(DealerProperties properties) {
    this.properties = properties;
    this.objectMapper = JsonMapper.builder().findAndAddModules().build();
    this.payloadCodec = new PokerPayloadCodec(objectMapper);
    this.deliveryMode = parseDeliveryMode(properties.getAcpDeliveryMode());
    this.agent = buildAgent();
  }

  @Override
  public JoinTableMessage sendInvitation(String playerId, InvitationMessage message) {
    boolean sent = sendToPlayer(
        playerId,
        MessageType.INVITATION,
        message.tableId(),
        null,
        message.playerId(),
        message,
        true
    );
    if (!sent) {
      return new JoinTableMessage(
          MessageType.JOIN_TABLE,
          message.tableId(),
          playerId,
          message.seatNumber(),
          false,
          "ACP invitation delivery failed"
      );
    }

    JoinTableMessage response = awaitJoinResponse(playerId, message.tableId());
    if (response != null) {
      return response;
    }

    return new JoinTableMessage(
        MessageType.JOIN_TABLE,
        message.tableId(),
        playerId,
        message.seatNumber(),
        false,
        "Timed out waiting for JOIN_TABLE over ACP"
    );
  }

  @Override
  public void sendHandStart(String playerId, HandStartMessage message) {
    sendToPlayer(
        playerId,
        MessageType.HAND_START,
        message.state().tableId(),
        message.state().handNumber(),
        playerId,
        message,
        false
    );
  }

  @Override
  public void sendHoleCards(String playerId, HoleCardsMessage message) {
    sendToPlayer(
        playerId,
        MessageType.HOLE_CARDS,
        message.tableId(),
        null,
        message.playerId(),
        message,
        false
    );
  }

  @Override
  public ActionResponseMessage requestAction(String playerId, ActionRequestMessage message) {
    boolean sent = sendToPlayer(
        playerId,
        MessageType.ACTION_REQUEST,
        message.tableId(),
        message.handNumber(),
        message.playerId(),
        message,
        true
    );
    if (!sent) {
      return null;
    }
    return awaitActionResponse(playerId, message.tableId());
  }

  @Override
  public void broadcastActionApplied(ActionAppliedMessage message) {
    broadcast(
        MessageType.ACTION_APPLIED,
        message.tableId(),
        message.handNumber(),
        message.playerId(),
        message
    );
  }

  @Override
  public void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
    broadcast(
        MessageType.COMMUNITY_CARDS_UPDATED,
        message.tableId(),
        message.handNumber(),
        null,
        message
    );
  }

  @Override
  public void broadcastHandResult(HandResultMessage message) {
    broadcast(
        MessageType.HAND_RESULT,
        message.tableId(),
        message.handNumber(),
        null,
        message
    );
  }

  @Override
  public void broadcastPlayerEliminated(PlayerEliminatedMessage message) {
    broadcast(
        MessageType.PLAYER_ELIMINATED,
        message.tableId(),
        null,
        message.playerId(),
        message
    );
  }

  @Override
  public void broadcastGameFinished(GameFinishedMessage message) {
    broadcast(
        MessageType.GAME_FINISHED,
        message.tableId(),
        null,
        message.winnerId(),
        message
    );
  }

  public InboundResult receive(Map<String, Object> rawMessage) {
    return agent.receive(rawMessage, null);
  }

  public void onInboundPayload(Map<String, Object> decryptedPayload) {
    PokerPayloadEvent event = toPayloadEvent(decryptedPayload);
    if (event == null) {
      return;
    }

    MessageType messageType = payloadCodec.resolveMessageType(event).orElse(null);
    if (messageType == null) {
      return;
    }

    switch (messageType) {
      case JOIN_TABLE -> payloadCodec.payloadAs(event, JoinTableMessage.class).ifPresent(this::bufferJoinResponse);
      case ACTION_RESPONSE -> payloadCodec.payloadAs(event, ActionResponseMessage.class).ifPresent(this::bufferActionResponse);
      default -> log.debug("Dealer ACP runtime ignoring inbound message type {}", messageType);
    }
  }

  public String getLocalAgentId() {
    return properties.getLocalAgentId();
  }

  public Map<String, Object> getIdentityDocument() {
    return agent.getIdentityDocument();
  }

  private void broadcast(
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String eventPlayerId,
      Object payload
  ) {
    for (String playerId : properties.getPlayerAgentIds().keySet()) {
      sendToPlayer(playerId, messageType, tableId, handNumber, eventPlayerId, payload, false);
    }
  }

  private boolean sendToPlayer(
      String playerId,
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String eventPlayerId,
      Object payload,
      boolean strict
  ) {
    String recipientAgentId = properties.getPlayerAgentIds().get(playerId);
    if (recipientAgentId == null || recipientAgentId.isBlank()) {
      String detail = "No ACP agent id configured for player " + playerId;
      if (strict) {
        throw new IllegalArgumentException(detail);
      }
      log.warn(detail);
      return false;
    }

    Map<String, Object> payloadMap = encodePayload(messageType, tableId, handNumber, eventPlayerId, payload);
    SendResult result = agent.send(
        List.of(recipientAgentId),
        payloadMap,
        "poker:" + tableId,
        deliveryMode
    );
    boolean delivered = isDelivered(result);
    if (!delivered) {
      String detail = summarizeFailure(result);
      if (strict) {
        throw new IllegalStateException("ACP send failed for " + playerId + ": " + detail);
      }
      log.warn("ACP send failed for {}: {}", playerId, detail);
    }
    return delivered;
  }

  private JoinTableMessage awaitJoinResponse(String playerId, String tableId) {
    long deadline = System.currentTimeMillis() + properties.getInviteTimeoutMillis();
    while (System.currentTimeMillis() < deadline) {
      JoinTableMessage message = pollJoinResponse(playerId, tableId);
      if (message != null) {
        return message;
      }
      sleep(properties.getAcpPollIntervalMillis());
    }
    return null;
  }

  private ActionResponseMessage awaitActionResponse(String playerId, String tableId) {
    long deadline = System.currentTimeMillis() + properties.getActionTimeoutMillis();
    while (System.currentTimeMillis() < deadline) {
      ActionResponseMessage message = pollActionResponse(playerId, tableId);
      if (message != null) {
        return message;
      }
      sleep(properties.getAcpPollIntervalMillis());
    }
    log.warn("Timed out waiting for ACTION_RESPONSE from {} over ACP", playerId);
    return null;
  }

  private void bufferJoinResponse(JoinTableMessage message) {
    Deque<JoinTableMessage> queue = joinResponses.computeIfAbsent(message.playerId(), ignored -> new ArrayDeque<>());
    synchronized (queue) {
      queue.addLast(message);
    }
  }

  private void bufferActionResponse(ActionResponseMessage message) {
    Deque<ActionResponseMessage> queue = actionResponses.computeIfAbsent(message.playerId(), ignored -> new ArrayDeque<>());
    synchronized (queue) {
      queue.addLast(message);
    }
  }

  private JoinTableMessage pollJoinResponse(String playerId, String tableId) {
    Deque<JoinTableMessage> queue = joinResponses.get(playerId);
    if (queue == null) {
      return null;
    }
    synchronized (queue) {
      return pollMatching(queue, message -> Objects.equals(tableId, message.tableId()));
    }
  }

  private ActionResponseMessage pollActionResponse(String playerId, String tableId) {
    Deque<ActionResponseMessage> queue = actionResponses.get(playerId);
    if (queue == null) {
      return null;
    }
    synchronized (queue) {
      return pollMatching(queue, message -> Objects.equals(tableId, message.tableId()));
    }
  }

  private static <T> T pollMatching(Deque<T> queue, java.util.function.Predicate<T> predicate) {
    int size = queue.size();
    for (int index = 0; index < size; index++) {
      T candidate = queue.removeFirst();
      if (predicate.test(candidate)) {
        return candidate;
      }
      queue.addLast(candidate);
    }
    return null;
  }

  private Map<String, Object> encodePayload(
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String playerId,
      Object payload
  ) {
    String payloadJson = payloadCodec.encode(
        messageType,
        tableId,
        handNumber,
        playerId,
        outboundSequence.incrementAndGet(),
        payload
    );
    try {
      return objectMapper.readValue(payloadJson, new TypeReference<>() {
      });
    } catch (Exception exception) {
      throw new IllegalStateException("Failed to encode ACP poker payload", exception);
    }
  }

  private PokerPayloadEvent toPayloadEvent(Map<String, Object> payload) {
    if (payload == null || payload.isEmpty()) {
      return null;
    }
    try {
      return objectMapper.convertValue(payload, PokerPayloadEvent.class);
    } catch (IllegalArgumentException exception) {
      log.warn("Unable to parse inbound ACP poker payload", exception);
      return null;
    }
  }

  private AcpAgent buildAgent() {
    AcpAgentOptions options = new AcpAgentOptions()
        .setStorageDir(Path.of(properties.getAcpStorageDir()))
        .setEndpoint(properties.resolveAcpEndpoint())
        .setDiscoveryScheme(properties.getAcpDiscoveryScheme())
        .setAllowInsecureHttp(properties.isAcpAllowInsecureHttp())
        .setAllowInsecureTls(properties.isAcpAllowInsecureTls())
        .setCaFile(properties.getAcpCaFile())
        .setDefaultDeliveryMode(deliveryMode);
    if (properties.getAcpRelayUrl() != null && !properties.getAcpRelayUrl().isBlank()) {
      options.setRelayUrl(properties.getAcpRelayUrl());
      options.setRelayHints(List.of(properties.getAcpRelayUrl()));
    }
    return AcpAgent.loadOrCreate(properties.getLocalAgentId(), options);
  }

  private boolean isDelivered(SendResult result) {
    if (result == null || result.getOutcomes() == null || result.getOutcomes().isEmpty()) {
      return false;
    }
    for (DeliveryOutcome outcome : result.getOutcomes()) {
      if (outcome != null
          && (outcome.getState() == DeliveryState.ACKNOWLEDGED || outcome.getState() == DeliveryState.DELIVERED)) {
        return true;
      }
    }
    return false;
  }

  private static String summarizeFailure(SendResult result) {
    if (result == null || result.getOutcomes() == null || result.getOutcomes().isEmpty()) {
      return "no delivery outcomes";
    }
    DeliveryOutcome first = result.getOutcomes().get(0);
    if (first == null) {
      return "empty delivery outcome";
    }
    return "state=" + first.getState()
        + ", reasonCode=" + first.getReasonCode()
        + ", detail=" + first.getDetail();
  }

  private static void sleep(long millis) {
    if (millis <= 0) {
      return;
    }
    try {
      Thread.sleep(millis);
    } catch (InterruptedException interrupted) {
      Thread.currentThread().interrupt();
    }
  }

  private static DeliveryMode parseDeliveryMode(String configured) {
    String normalized = configured == null ? "direct" : configured.trim().toUpperCase(Locale.ROOT);
    try {
      return DeliveryMode.valueOf(normalized);
    } catch (Exception ignored) {
      return DeliveryMode.DIRECT;
    }
  }
}
