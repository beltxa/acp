package com.cooperate.poker.dealer.service;

import com.cooperate.poker.common.messaging.DealerOutboundChannel;
import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.GameStatus;
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
import com.cooperate.poker.dealer.config.DealerProperties;
import com.cooperate.poker.dealer.engine.DeckService;
import com.cooperate.poker.dealer.engine.PokerEngineAdapter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DefaultDealerServiceStartupBehaviorTest {

  @Test
  void startupDoesNotAutoStartGameLoopOrSendMessages() {
    CountingDealerOutboundChannel outbound = new CountingDealerOutboundChannel();

    DefaultDealerService service = new DefaultDealerService(
        new DealerProperties(),
        outbound,
        new TableStateRepository(),
        new DeckService(),
        new PokerEngineAdapter()
    );

    assertThat(service.isRunning()).isFalse();
    assertThat(service.getCurrentTableState()).isNotNull();
    assertThat(service.getCurrentTableState().status()).isEqualTo(GameStatus.WAITING_FOR_PLAYERS);
    assertThat(service.getCurrentTableState().gameState().handNumber()).isZero();
    assertThat(outbound.totalInvocations()).isZero();
  }

  private static final class CountingDealerOutboundChannel implements DealerOutboundChannel {
    private int invitationCalls;
    private int handStartCalls;
    private int holeCardsCalls;
    private int actionRequestCalls;
    private int actionAppliedBroadcasts;
    private int communityCardsBroadcasts;
    private int handResultBroadcasts;
    private int playerEliminatedBroadcasts;
    private int gameFinishedBroadcasts;

    @Override
    public JoinTableMessage sendInvitation(String playerId, InvitationMessage message) {
      invitationCalls += 1;
      return new JoinTableMessage(
          MessageType.JOIN_TABLE,
          message.tableId(),
          playerId,
          message.seatNumber(),
          true,
          "joined"
      );
    }

    @Override
    public void sendHandStart(String playerId, HandStartMessage message) {
      handStartCalls += 1;
    }

    @Override
    public void sendHoleCards(String playerId, HoleCardsMessage message) {
      holeCardsCalls += 1;
    }

    @Override
    public ActionResponseMessage requestAction(String playerId, ActionRequestMessage message) {
      actionRequestCalls += 1;
      return new ActionResponseMessage(
          MessageType.ACTION_RESPONSE,
          message.tableId(),
          playerId,
          new PlayerAction(ActionType.CHECK, 0, "test")
      );
    }

    @Override
    public void broadcastActionApplied(ActionAppliedMessage message) {
      actionAppliedBroadcasts += 1;
    }

    @Override
    public void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
      communityCardsBroadcasts += 1;
    }

    @Override
    public void broadcastHandResult(HandResultMessage message) {
      handResultBroadcasts += 1;
    }

    @Override
    public void broadcastPlayerEliminated(PlayerEliminatedMessage message) {
      playerEliminatedBroadcasts += 1;
    }

    @Override
    public void broadcastGameFinished(GameFinishedMessage message) {
      gameFinishedBroadcasts += 1;
    }

    private int totalInvocations() {
      return invitationCalls
          + handStartCalls
          + holeCardsCalls
          + actionRequestCalls
          + actionAppliedBroadcasts
          + communityCardsBroadcasts
          + handResultBroadcasts
          + playerEliminatedBroadcasts
          + gameFinishedBroadcasts;
    }
  }
}
