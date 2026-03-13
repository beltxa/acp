package com.cooperate.poker.common.messaging;

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

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class LocalDealerOutboundChannel implements DealerOutboundChannel {
  private final Map<String, PlayerEndpoint> players = new ConcurrentHashMap<>();

  public void registerPlayer(String playerId, PlayerEndpoint endpoint) {
    players.put(playerId, endpoint);
  }

  public void unregisterPlayer(String playerId) {
    players.remove(playerId);
  }

  @Override
  public JoinTableMessage sendInvitation(String playerId, InvitationMessage message) {
    return endpoint(playerId).onInvitation(message);
  }

  @Override
  public void sendHandStart(String playerId, HandStartMessage message) {
    endpoint(playerId).onHandStart(message);
  }

  @Override
  public void sendHoleCards(String playerId, HoleCardsMessage message) {
    endpoint(playerId).onHoleCards(message);
  }

  @Override
  public ActionResponseMessage requestAction(String playerId, ActionRequestMessage message) {
    return endpoint(playerId).onActionRequest(message);
  }

  @Override
  public void broadcastActionApplied(ActionAppliedMessage message) {
    players.values().forEach(p -> p.onActionApplied(message));
  }

  @Override
  public void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
    players.values().forEach(p -> p.onCommunityCardsUpdated(message));
  }

  @Override
  public void broadcastHandResult(HandResultMessage message) {
    players.values().forEach(p -> p.onHandResult(message));
  }

  @Override
  public void broadcastPlayerEliminated(PlayerEliminatedMessage message) {
    players.values().forEach(p -> p.onPlayerEliminated(message));
  }

  @Override
  public void broadcastGameFinished(GameFinishedMessage message) {
    players.values().forEach(p -> p.onGameFinished(message));
  }

  private PlayerEndpoint endpoint(String playerId) {
    PlayerEndpoint endpoint = players.get(playerId);
    if (endpoint == null) {
      throw new IllegalStateException("No registered local player endpoint for " + playerId);
    }
    return endpoint;
  }
}
