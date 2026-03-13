package com.cooperate.poker.dealer.service;

import com.cooperate.poker.common.messaging.DealerOutboundChannel;
import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.RoundType;
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

import java.time.Duration;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class DefaultDealerServiceOrderingTest {

  @Test
  void startGameDealsAndActsInRotatingClockwiseOrder() throws Exception {
    DealerProperties properties = new DealerProperties();
    properties.setSpectatorDelayMillis(0);
    properties.setAnte(0);
    properties.setSmallBlind(1);
    properties.setBigBlind(2);
    properties.setMaxHands(3);

    CapturingDealerOutboundChannel outbound = new CapturingDealerOutboundChannel();
    DefaultDealerService service = new DefaultDealerService(
        properties,
        outbound,
        new TableStateRepository(),
        new DeckService(),
        new PokerEngineAdapter()
    );

    service.startGame();
    waitForCompletion(service, Duration.ofSeconds(10));

    Map<Integer, List<String>> expectedOrderByHand = Map.of(
        1, List.of("Player-1", "Player-2", "Player-3", "Player-4"),
        2, List.of("Player-2", "Player-3", "Player-4", "Player-1"),
        3, List.of("Player-3", "Player-4", "Player-1", "Player-2")
    );

    assertThat(outbound.holeCardOrderByHand).containsKeys(1, 2, 3);
    assertThat(outbound.holeCardOrderByHand.get(1)).containsExactlyElementsOf(expectedOrderByHand.get(1));
    assertThat(outbound.holeCardOrderByHand.get(2)).containsExactlyElementsOf(expectedOrderByHand.get(2));
    assertThat(outbound.holeCardOrderByHand.get(3)).containsExactlyElementsOf(expectedOrderByHand.get(3));

    assertThat(outbound.requestedActionOrderByHandAndRound).containsKeys(1, 2, 3);
    for (Map.Entry<Integer, List<String>> expected : expectedOrderByHand.entrySet()) {
      int handNumber = expected.getKey();
      List<String> order = expected.getValue();
      assertThat(outbound.requestedActionOrderByHandAndRound.get(handNumber).get(RoundType.PRE_FLOP))
          .containsExactlyElementsOf(order);
      assertThat(outbound.requestedActionOrderByHandAndRound.get(handNumber).get(RoundType.FLOP))
          .containsExactlyElementsOf(order);
      assertThat(outbound.requestedActionOrderByHandAndRound.get(handNumber).get(RoundType.TURN))
          .containsExactlyElementsOf(order);
      assertThat(outbound.requestedActionOrderByHandAndRound.get(handNumber).get(RoundType.RIVER))
          .containsExactlyElementsOf(order);
    }

    assertThat(outbound.holeCardTargetMismatches).isEmpty();
    assertThat(outbound.handStartPrivacyLeaks).isEmpty();
  }

  private static void waitForCompletion(DefaultDealerService service, Duration timeout) throws InterruptedException {
    long deadline = System.nanoTime() + timeout.toNanos();
    while (service.isRunning() && System.nanoTime() < deadline) {
      Thread.sleep(20L);
    }
    assertThat(service.isRunning()).isFalse();
  }

  private static final class CapturingDealerOutboundChannel implements DealerOutboundChannel {
    private final Map<String, Integer> latestHandByPlayer = new LinkedHashMap<>();
    private final Map<Integer, List<String>> holeCardOrderByHand = new LinkedHashMap<>();
    private final Map<Integer, Map<RoundType, List<String>>> requestedActionOrderByHandAndRound = new LinkedHashMap<>();
    private final List<String> holeCardTargetMismatches = new ArrayList<>();
    private final List<String> handStartPrivacyLeaks = new ArrayList<>();

    @Override
    public JoinTableMessage sendInvitation(String playerId, InvitationMessage message) {
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
      latestHandByPlayer.put(playerId, message.state().handNumber());
      message.state().playerStates().forEach((seenPlayerId, playerState) -> {
        if (!playerId.equals(seenPlayerId) && playerState.holeCards() != null && !playerState.holeCards().isEmpty()) {
          handStartPrivacyLeaks.add(playerId + " saw hole cards for " + seenPlayerId);
        }
      });
    }

    @Override
    public void sendHoleCards(String playerId, HoleCardsMessage message) {
      if (!playerId.equals(message.playerId())) {
        holeCardTargetMismatches.add("target=" + playerId + " payloadPlayer=" + message.playerId());
      }
      Integer handNumber = latestHandByPlayer.get(playerId);
      if (handNumber != null) {
        holeCardOrderByHand.computeIfAbsent(handNumber, ignored -> new ArrayList<>()).add(playerId);
      }
    }

    @Override
    public ActionResponseMessage requestAction(String playerId, ActionRequestMessage message) {
      requestedActionOrderByHandAndRound
          .computeIfAbsent(message.handNumber(), ignored -> new EnumMap<>(RoundType.class))
          .computeIfAbsent(message.roundType(), ignored -> new ArrayList<>())
          .add(playerId);

      int toCall = Math.max(0, message.currentBet() - message.committedBet());
      PlayerAction responseAction;
      if (toCall > 0 && message.legalActions().contains(ActionType.CALL)) {
        responseAction = new PlayerAction(ActionType.CALL, toCall, "test call");
      } else if (toCall == 0 && message.legalActions().contains(ActionType.CHECK)) {
        responseAction = new PlayerAction(ActionType.CHECK, 0, "test check");
      } else if (message.legalActions().contains(ActionType.FOLD)) {
        responseAction = new PlayerAction(ActionType.FOLD, 0, "test fold");
      } else {
        responseAction = new PlayerAction(message.legalActions().getFirst(), 0, "test fallback");
      }
      return new ActionResponseMessage(
          MessageType.ACTION_RESPONSE,
          message.tableId(),
          playerId,
          responseAction
      );
    }

    @Override
    public void broadcastActionApplied(ActionAppliedMessage message) {
    }

    @Override
    public void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
    }

    @Override
    public void broadcastHandResult(HandResultMessage message) {
    }

    @Override
    public void broadcastPlayerEliminated(PlayerEliminatedMessage message) {
    }

    @Override
    public void broadcastGameFinished(GameFinishedMessage message) {
    }
  }
}
