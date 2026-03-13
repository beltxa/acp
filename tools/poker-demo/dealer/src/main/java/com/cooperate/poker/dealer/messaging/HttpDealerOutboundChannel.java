package com.cooperate.poker.dealer.messaging;

import com.cooperate.poker.common.messaging.DealerOutboundChannel;
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
import com.cooperate.poker.common.protocol.PlayerEliminatedMessage;
import com.cooperate.poker.common.protocol.ProtocolPaths;
import com.cooperate.poker.dealer.config.DealerProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Component
@ConditionalOnProperty(name = "poker.dealer.transport-mode", havingValue = "HTTP")
public class HttpDealerOutboundChannel implements DealerOutboundChannel {
  private final RestClient restClient;
  private final DealerProperties properties;

  public HttpDealerOutboundChannel(DealerProperties properties) {
    this.properties = properties;
    this.restClient = RestClient.builder().build();
  }

  @Override
  public JoinTableMessage sendInvitation(String playerId, InvitationMessage message) {
    return postForBody(playerId, ProtocolPaths.INVITATION, message, JoinTableMessage.class);
  }

  @Override
  public void sendHandStart(String playerId, HandStartMessage message) {
    postWithoutBody(playerId, ProtocolPaths.HAND_START, message);
  }

  @Override
  public void sendHoleCards(String playerId, HoleCardsMessage message) {
    postWithoutBody(playerId, ProtocolPaths.HOLE_CARDS, message);
  }

  @Override
  public ActionResponseMessage requestAction(String playerId, ActionRequestMessage message) {
    return postForBody(playerId, ProtocolPaths.ACTION_REQUEST, message, ActionResponseMessage.class);
  }

  @Override
  public void broadcastActionApplied(ActionAppliedMessage message) {
    broadcast(ProtocolPaths.ACTION_APPLIED, message);
  }

  @Override
  public void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
    broadcast(ProtocolPaths.COMMUNITY_CARDS_UPDATED, message);
  }

  @Override
  public void broadcastHandResult(HandResultMessage message) {
    broadcast(ProtocolPaths.HAND_RESULT, message);
  }

  @Override
  public void broadcastPlayerEliminated(PlayerEliminatedMessage message) {
    broadcast(ProtocolPaths.PLAYER_ELIMINATED, message);
  }

  @Override
  public void broadcastGameFinished(GameFinishedMessage message) {
    broadcast(ProtocolPaths.GAME_FINISHED, message);
  }

  private void broadcast(String path, Object message) {
    for (String playerId : properties.getPlayerEndpoints().keySet()) {
      postWithoutBody(playerId, path, message);
    }
  }

  private <T> T postForBody(String playerId, String path, Object body, Class<T> responseType) {
    String endpoint = resolveEndpoint(playerId) + path;
    try {
      return restClient.post()
          .uri(endpoint)
          .body(body)
          .retrieve()
          .body(responseType);
    } catch (RuntimeException exception) {
      throw new IllegalStateException("Failed to POST " + path + " to " + playerId + " at " + endpoint, exception);
    }
  }

  private void postWithoutBody(String playerId, String path, Object body) {
    String endpoint = resolveEndpoint(playerId) + path;
    try {
      restClient.post()
          .uri(endpoint)
          .body(body)
          .retrieve()
          .toBodilessEntity();
    } catch (RuntimeException exception) {
      throw new IllegalStateException("Failed to POST " + path + " to " + playerId + " at " + endpoint, exception);
    }
  }

  private String resolveEndpoint(String playerId) {
    Map<String, String> endpoints = properties.getPlayerEndpoints();
    String endpoint = endpoints.get(playerId);
    if (endpoint == null || endpoint.isBlank()) {
      throw new IllegalArgumentException("No endpoint configured for player " + playerId);
    }
    return endpoint;
  }
}
