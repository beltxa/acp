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

public interface PlayerEndpoint {
  JoinTableMessage onInvitation(InvitationMessage message);

  void onHandStart(HandStartMessage message);

  void onHoleCards(HoleCardsMessage message);

  ActionResponseMessage onActionRequest(ActionRequestMessage message);

  void onActionApplied(ActionAppliedMessage message);

  void onCommunityCardsUpdated(CommunityCardsUpdatedMessage message);

  void onHandResult(HandResultMessage message);

  void onPlayerEliminated(PlayerEliminatedMessage message);

  void onGameFinished(GameFinishedMessage message);
}
