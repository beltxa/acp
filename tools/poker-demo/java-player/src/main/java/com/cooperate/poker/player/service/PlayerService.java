package com.cooperate.poker.player.service;

import com.cooperate.poker.common.messaging.PlayerEndpoint;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
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
import com.cooperate.poker.player.agent.AgentDecisionService;
import com.cooperate.poker.player.config.PlayerProperties;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

@Service
public class PlayerService implements PlayerEndpoint {
  private static final Logger log = LoggerFactory.getLogger(PlayerService.class);

  private final PlayerProperties properties;
  private final AgentDecisionService decisionService;

  private final AtomicBoolean eliminated = new AtomicBoolean(false);
  private volatile String activeTableId;
  private volatile int lastHandNumber;
  private final List<String> holeCards = new ArrayList<>(2);

  public PlayerService(PlayerProperties properties, AgentDecisionService decisionService) {
    this.properties = properties;
    this.decisionService = decisionService;
  }

  @PostConstruct
  void bootLog() {
    log.info("Player {} ({}) started with provider={} model={} personality={}",
        properties.getPlayerId(),
        properties.getEntityId(),
        properties.getLlmProvider(),
        properties.getModel(),
        properties.getPersonality());
  }

  @Override
  public JoinTableMessage onInvitation(InvitationMessage message) {
    boolean accepted = properties.getPlayerId().equals(message.playerId());
    if (accepted) {
      activeTableId = message.tableId();
      eliminated.set(false);
    }

    return new JoinTableMessage(
        MessageType.JOIN_TABLE,
        message.tableId(),
        properties.getPlayerId(),
        message.seatNumber(),
        accepted,
        accepted ? "joined" : "player id mismatch"
    );
  }

  @Override
  public void onHandStart(HandStartMessage message) {
    lastHandNumber = message.state().handNumber();
    log.info("{} received HAND_START for hand {}", properties.getPlayerId(), lastHandNumber);
  }

  @Override
  public void onHoleCards(HoleCardsMessage message) {
    synchronized (holeCards) {
      holeCards.clear();
      holeCards.addAll(message.holeCards());
    }
    log.info("{} received hole cards {}", properties.getPlayerId(), message.holeCards());
  }

  @Override
  public ActionResponseMessage onActionRequest(ActionRequestMessage message) {
    if (eliminated.get()) {
      return new ActionResponseMessage(
          MessageType.ACTION_RESPONSE,
          message.tableId(),
          properties.getPlayerId(),
          new PlayerAction(com.cooperate.poker.common.model.ActionType.FOLD, 0, "eliminated")
      );
    }

    PlayerAction action = decisionService.decideAction(message);
    return new ActionResponseMessage(
        MessageType.ACTION_RESPONSE,
        message.tableId(),
        properties.getPlayerId(),
        action
    );
  }

  @Override
  public void onActionApplied(ActionAppliedMessage message) {
    log.debug("{} observed {} action {}", properties.getPlayerId(), message.playerId(), message.action());
  }

  @Override
  public void onCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
    log.debug("{} observed community cards {}", properties.getPlayerId(), message.communityCards());
  }

  @Override
  public void onHandResult(HandResultMessage message) {
    log.info("{} received hand result winners={} payouts={}", properties.getPlayerId(), message.winnerIds(), message.amountWonByPlayer());
  }

  @Override
  public void onPlayerEliminated(PlayerEliminatedMessage message) {
    if (properties.getPlayerId().equals(message.playerId())) {
      eliminated.set(true);
      log.info("{} has been eliminated", properties.getPlayerId());
    }
  }

  @Override
  public void onGameFinished(GameFinishedMessage message) {
    log.info("{} received GAME_FINISHED winner={} finalStacks={}", properties.getPlayerId(), message.winnerId(), message.finalStacks());
  }

  public boolean isEliminated() {
    return eliminated.get();
  }
}
