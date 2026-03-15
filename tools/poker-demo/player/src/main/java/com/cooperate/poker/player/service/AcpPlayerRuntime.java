package com.cooperate.poker.player.service;

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
import com.cooperate.poker.player.config.PlayerProperties;
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
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

@Component
@ConditionalOnProperty(name = "poker.player.transport-mode", havingValue = "ACP")
public class AcpPlayerRuntime {
  private static final Logger log = LoggerFactory.getLogger(AcpPlayerRuntime.class);

  private final PlayerProperties properties;
  private final PlayerService playerService;
  private final ObjectMapper objectMapper;
  private final PokerPayloadCodec payloadCodec;
  private final AcpAgent agent;
  private final DeliveryMode deliveryMode;
  private final AtomicInteger outboundSequence = new AtomicInteger(0);

  public AcpPlayerRuntime(PlayerProperties properties, PlayerService playerService) {
    this.properties = properties;
    this.playerService = playerService;
    this.objectMapper = JsonMapper.builder().findAndAddModules().build();
    this.payloadCodec = new PokerPayloadCodec(objectMapper);
    this.deliveryMode = parseDeliveryMode(properties.getAcpDeliveryMode());
    this.agent = buildAgent();
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

    try {
      switch (messageType) {
        case INVITATION -> payloadCodec.payloadAs(event, InvitationMessage.class).ifPresent(invitation -> {
          JoinTableMessage response = playerService.onInvitation(invitation);
          sendToDealer(
              MessageType.JOIN_TABLE,
              invitation.tableId(),
              null,
              response.playerId(),
              response
          );
        });
        case HAND_START -> payloadCodec.payloadAs(event, HandStartMessage.class).ifPresent(playerService::onHandStart);
        case HOLE_CARDS -> payloadCodec.payloadAs(event, HoleCardsMessage.class).ifPresent(playerService::onHoleCards);
        case ACTION_REQUEST -> payloadCodec.payloadAs(event, ActionRequestMessage.class).ifPresent(request -> {
          ActionResponseMessage response = playerService.onActionRequest(request);
          sendToDealer(
              MessageType.ACTION_RESPONSE,
              request.tableId(),
              request.handNumber(),
              response.playerId(),
              response
          );
        });
        case ACTION_APPLIED -> payloadCodec.payloadAs(event, ActionAppliedMessage.class).ifPresent(playerService::onActionApplied);
        case COMMUNITY_CARDS_UPDATED -> payloadCodec.payloadAs(event, CommunityCardsUpdatedMessage.class)
            .ifPresent(playerService::onCommunityCardsUpdated);
        case HAND_RESULT -> payloadCodec.payloadAs(event, HandResultMessage.class).ifPresent(playerService::onHandResult);
        case PLAYER_ELIMINATED -> payloadCodec.payloadAs(event, PlayerEliminatedMessage.class).ifPresent(playerService::onPlayerEliminated);
        case GAME_FINISHED -> payloadCodec.payloadAs(event, GameFinishedMessage.class).ifPresent(playerService::onGameFinished);
        case JOIN_TABLE, ACTION_RESPONSE -> log.debug("Player runtime ignoring inbound message type {}", messageType);
      }
    } catch (RuntimeException exception) {
      log.warn("Failed to process inbound ACP poker payload for {}", properties.getPlayerId(), exception);
    }
  }

  public String getLocalAgentId() {
    return properties.getLocalAgentId();
  }

  public Map<String, Object> getIdentityDocument() {
    return agent.getIdentityDocument();
  }

  public Map<String, Object> getWellKnownDocument() {
    return agent.buildWellKnownDocument(properties.getPublicBaseUrl());
  }

  private void sendToDealer(
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String playerId,
      Object payload
  ) {
    Map<String, Object> payloadMap = encodePayload(messageType, tableId, handNumber, playerId, payload);
    SendResult result = agent.send(
        List.of(properties.getDealerAgentId()),
        payloadMap,
        "poker:" + tableId,
        deliveryMode
    );
    if (!isDelivered(result)) {
      log.warn("ACP send failed from {} to dealer: {}", properties.getPlayerId(), summarizeFailure(result));
    }
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

  private static boolean isDelivered(SendResult result) {
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

  private static DeliveryMode parseDeliveryMode(String configured) {
    String normalized = configured == null ? "direct" : configured.trim().toUpperCase(Locale.ROOT);
    try {
      return DeliveryMode.valueOf(normalized);
    } catch (Exception ignored) {
      return DeliveryMode.DIRECT;
    }
  }
}
