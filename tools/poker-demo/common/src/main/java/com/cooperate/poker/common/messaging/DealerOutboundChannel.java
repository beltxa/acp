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

public interface DealerOutboundChannel {
  JoinTableMessage sendInvitation(String playerId, InvitationMessage message);

  void sendHandStart(String playerId, HandStartMessage message);

  void sendHoleCards(String playerId, HoleCardsMessage message);

  ActionResponseMessage requestAction(String playerId, ActionRequestMessage message);

  void broadcastActionApplied(ActionAppliedMessage message);

  void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message);

  void broadcastHandResult(HandResultMessage message);

  void broadcastPlayerEliminated(PlayerEliminatedMessage message);

  void broadcastGameFinished(GameFinishedMessage message);

  default void closeSession(String reason) {
    // Optional transport-specific lifecycle hook.
  }
}
