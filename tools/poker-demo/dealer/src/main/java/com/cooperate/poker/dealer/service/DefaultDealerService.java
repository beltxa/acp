package com.cooperate.poker.dealer.service;

import com.cooperate.poker.common.messaging.DealerOutboundChannel;
import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.GameState;
import com.cooperate.poker.common.model.GameStatus;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.PlayerState;
import com.cooperate.poker.common.model.PlayerStatus;
import com.cooperate.poker.common.model.RoundType;
import com.cooperate.poker.common.model.SeatState;
import com.cooperate.poker.common.model.TableState;
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
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

@Service
public class DefaultDealerService implements DealerService {
  private static final Logger log = LoggerFactory.getLogger(DefaultDealerService.class);

  private final DealerProperties properties;
  private final DealerOutboundChannel outboundChannel;
  private final TableStateRepository repository;
  private final DeckService deckService;
  private final PokerEngineAdapter pokerEngineAdapter;

  private final AtomicReference<RuntimeTable> runtimeRef = new AtomicReference<>();
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final ExecutorService loopExecutor = Executors.newSingleThreadExecutor(r -> {
    Thread thread = new Thread(r, "poker-dealer-loop");
    thread.setDaemon(true);
    return thread;
  });

  public DefaultDealerService(
      DealerProperties properties,
      DealerOutboundChannel outboundChannel,
      TableStateRepository repository,
      DeckService deckService,
      PokerEngineAdapter pokerEngineAdapter
  ) {
    this.properties = properties;
    this.outboundChannel = outboundChannel;
    this.repository = repository;
    this.deckService = deckService;
    this.pokerEngineAdapter = pokerEngineAdapter;

    RuntimeTable initial = newRuntimeTable();
    runtimeRef.set(initial);
    publishSnapshot(initial);
  }

  @Override
  public void startGame() {
    if (!running.compareAndSet(false, true)) {
      return;
    }

    RuntimeTable table = newRuntimeTable();
    runtimeRef.set(table);
    appendAction(table, "Game loop started");
    publishSnapshot(table);

    loopExecutor.submit(() -> {
      try {
        invitePlayers(table);
        if (table.status != GameStatus.READY) {
          appendAction(table, "Unable to start game because table is not ready");
          return;
        }

        table.status = GameStatus.IN_PROGRESS;
        appendAction(table, "All players joined. Starting gameplay");
        publishSnapshot(table);

        while (!isGameOver(table) && table.handNumber < properties.getMaxHands()) {
          startHandInternal(table);
          pauseForSpectators();

          if (activePlayersInHand(table).size() > 1) {
            runBettingRoundInternal(table, RoundType.PRE_FLOP);
          }
          if (activePlayersInHand(table).size() > 1) {
            revealCommunityCards(table, RoundType.FLOP, 3);
            pauseForSpectators();
            runBettingRoundInternal(table, RoundType.FLOP);
          }
          if (activePlayersInHand(table).size() > 1) {
            revealCommunityCards(table, RoundType.TURN, 1);
            pauseForSpectators();
            runBettingRoundInternal(table, RoundType.TURN);
          }
          if (activePlayersInHand(table).size() > 1) {
            revealCommunityCards(table, RoundType.RIVER, 1);
            pauseForSpectators();
            runBettingRoundInternal(table, RoundType.RIVER);
          }

          resolveHandInternal(table);
          pauseForSpectators();
          eliminatePlayersInternal(table);
        }
      } catch (Exception exception) {
        log.error("Dealer loop failed", exception);
        appendAction(table, "Dealer error: " + exception.getMessage());
      } finally {
        finishGameInternal(table);
        running.set(false);
        publishSnapshot(table);
      }
    });
  }

  @Override
  public void resetGame() {
    RuntimeTable table = newRuntimeTable();
    table.status = GameStatus.WAITING_FOR_PLAYERS;
    appendAction(table, "Game reset");
    runtimeRef.set(table);
    publishSnapshot(table);
  }

  @Override
  public void startHand() {
    RuntimeTable table = runtimeRef.get();
    if (table == null || running.get()) {
      return;
    }
    startHandInternal(table);
    publishSnapshot(table);
  }

  @Override
  public void runBettingRound() {
    RuntimeTable table = runtimeRef.get();
    if (table == null || running.get()) {
      return;
    }

    RoundType roundType = table.roundType == null ? RoundType.PRE_FLOP : table.roundType;
    runBettingRoundInternal(table, roundType);
    publishSnapshot(table);
  }

  @Override
  public void resolveHand() {
    RuntimeTable table = runtimeRef.get();
    if (table == null || running.get()) {
      return;
    }
    resolveHandInternal(table);
    publishSnapshot(table);
  }

  @Override
  public void eliminatePlayers() {
    RuntimeTable table = runtimeRef.get();
    if (table == null || running.get()) {
      return;
    }
    eliminatePlayersInternal(table);
    publishSnapshot(table);
  }

  @Override
  public void finishGame() {
    RuntimeTable table = runtimeRef.get();
    if (table == null) {
      return;
    }
    finishGameInternal(table);
    publishSnapshot(table);
  }

  @Override
  public TableState getCurrentTableState() {
    return repository.get();
  }

  @Override
  public boolean isRunning() {
    return running.get();
  }

  @PreDestroy
  public void shutdown() {
    loopExecutor.shutdownNow();
  }

  private RuntimeTable newRuntimeTable() {
    RuntimeTable table = new RuntimeTable(properties.getTableId(), properties.getBigBlind());

    int seatNumber = 1;
    for (String playerId : configuredPlayerIds()) {
      table.players.put(playerId, new RuntimePlayer(playerId, seatNumber++, properties.getStartingStack()));
    }

    table.status = GameStatus.WAITING_FOR_PLAYERS;
    table.roundType = RoundType.PRE_FLOP;
    return table;
  }

  private void invitePlayers(RuntimeTable table) {
    table.status = GameStatus.INVITING_PLAYERS;
    appendAction(table, "Inviting players");
    publishSnapshot(table);

    for (RuntimePlayer player : orderedPlayers(table)) {
      InvitationMessage invitation = new InvitationMessage(
          MessageType.INVITATION,
          table.tableId,
          player.playerId,
          player.seatNumber
      );

      JoinTableMessage response = outboundChannel.sendInvitation(player.playerId, invitation);
      if (response == null || !response.accepted()) {
        throw new IllegalStateException("Player did not accept invitation: " + player.playerId);
      }

      player.joined = true;
      player.status = PlayerStatus.ACTIVE;
      appendAction(table, player.playerId + " joined seat " + player.seatNumber);
      publishSnapshot(table);
    }

    long joinedCount = table.players.values().stream().filter(p -> p.joined).count();
    if (joinedCount == table.players.size()) {
      table.status = GameStatus.READY;
      appendAction(table, "Table ready with all players seated");
      publishSnapshot(table);
    }
  }

  private void startHandInternal(RuntimeTable table) {
    if (table.status == GameStatus.FINISHED) {
      return;
    }

    List<RuntimePlayer> participants = eligiblePlayers(table);
    if (participants.size() < 2) {
      finishGameInternal(table);
      return;
    }

    table.handNumber += 1;
    table.roundType = RoundType.PRE_FLOP;
    table.communityCards.clear();
    table.pot = 0;
    table.currentBet = 0;
    table.minRaise = properties.getBigBlind();

    for (RuntimePlayer player : table.players.values()) {
      player.holeCards.clear();
      player.committedBet = 0;
      player.lastAction = null;
      player.lastHandDelta = 0;
      player.handStartStack = player.stack;
      if (player.stack <= 0) {
        player.status = PlayerStatus.ELIMINATED;
      } else if (player.joined) {
        player.status = PlayerStatus.ACTIVE;
      }
    }

    collectAntes(table);

    table.deck.clear();
    table.deck.addAll(deckService.shuffle());

    table.dealerButtonSeat = nextActiveSeat(table, table.dealerButtonSeat);
    table.smallBlindSeat = nextActiveSeat(table, table.dealerButtonSeat);
    table.bigBlindSeat = nextActiveSeat(table, table.smallBlindSeat);

    RuntimePlayer smallBlindPlayer = playerAtSeat(table, table.smallBlindSeat);
    RuntimePlayer bigBlindPlayer = playerAtSeat(table, table.bigBlindSeat);

    postBlind(table, smallBlindPlayer, properties.getSmallBlind(), "small blind");
    postBlind(table, bigBlindPlayer, properties.getBigBlind(), "big blind");

    List<RuntimePlayer> dealingOrder = orderedPlayersFromSeat(table, table.dealerButtonSeat).stream()
        .filter(this::isInCurrentHand)
        .toList();
    table.currentHandOrderPlayerIds.clear();
    for (RuntimePlayer player : dealingOrder) {
      table.currentHandOrderPlayerIds.add(player.playerId);
    }
    for (int cardRound = 0; cardRound < 2; cardRound++) {
      for (RuntimePlayer player : dealingOrder) {
        player.holeCards.add(deckService.dealCard(table.deck));
      }
    }

    for (RuntimePlayer player : dealingOrder) {
      outboundChannel.sendHandStart(
          player.playerId,
          new HandStartMessage(MessageType.HAND_START, toPlayerGameState(table, player.playerId))
      );
      outboundChannel.sendHoleCards(
          player.playerId,
          new HoleCardsMessage(MessageType.HOLE_CARDS, table.tableId, player.playerId, player.holeCards)
      );
    }

    appendAction(table, "Hand " + table.handNumber + " started");
    appendAction(
        table,
        "Dealer button seat " + table.dealerButtonSeat + ", SB seat " + table.smallBlindSeat + ", BB seat " + table.bigBlindSeat
    );
    publishSnapshot(table);
  }

  private void runBettingRoundInternal(RuntimeTable table, RoundType roundType) {
    if (table.status == GameStatus.FINISHED || activePlayersInHand(table).size() <= 1) {
      return;
    }

    table.roundType = roundType;
    if (roundType != RoundType.PRE_FLOP) {
      table.currentBet = 0;
      for (RuntimePlayer player : table.players.values()) {
        if (isInCurrentHand(player)) {
          player.committedBet = 0;
          if (player.status == PlayerStatus.ALL_IN && player.stack > 0) {
            player.status = PlayerStatus.ACTIVE;
          }
        }
      }
    }

    appendAction(table, "Round " + roundType + " started");
    publishSnapshot(table);

    List<RuntimePlayer> order = currentHandOrder(table);
    if (order.isEmpty()) {
      return;
    }

    Set<String> pending = order.stream()
        .filter(this::canAct)
        .map(player -> player.playerId)
        .collect(Collectors.toCollection(LinkedHashSet::new));

    while (!pending.isEmpty() && activePlayersInHand(table).size() > 1) {
      String currentPlayerId = first(pending);
      pending.remove(currentPlayerId);

      RuntimePlayer player = table.players.get(currentPlayerId);
      if (player == null || !canAct(player)) {
        continue;
      }

      table.currentPlayerId = player.playerId;
      List<ActionType> legalActions = legalActions(table, player);
      ActionRequestMessage request = new ActionRequestMessage(
          MessageType.ACTION_REQUEST,
          table.tableId,
          table.handNumber,
          table.roundType,
          player.playerId,
          player.holeCards,
          table.communityCards,
          table.pot,
          table.currentBet,
          table.minRaise,
          player.stack,
          player.committedBet,
          legalActions
      );

      ActionResponseMessage response;
      try {
        response = outboundChannel.requestAction(player.playerId, request);
      } catch (Exception exception) {
        log.warn("Action request failed for {}", player.playerId, exception);
        response = null;
      }

      PlayerAction action = normalizeAction(table, player, response == null ? null : response.action(), legalActions);
      applyAction(table, player, action);
      outboundChannel.broadcastActionApplied(
          new ActionAppliedMessage(
              MessageType.ACTION_APPLIED,
              table.tableId,
              table.handNumber,
              table.roundType,
              player.playerId,
              action,
              table.pot,
              player.stack,
              table.currentBet
          )
      );

      if (action.reason() != null && !action.reason().isBlank()) {
        appendReasoning(table, player.playerId + ": " + action.reason());
      }

      if (action.action() == ActionType.BET || action.action() == ActionType.RAISE) {
        pending.clear();
        for (RuntimePlayer candidate : playersAfter(order, player.playerId)) {
          if (canAct(candidate)) {
            pending.add(candidate.playerId);
          }
        }
      }

      if (table.currentBet > 0 && allBetsMatched(table)) {
        pending.removeIf(playerId -> {
          RuntimePlayer candidate = table.players.get(playerId);
          return candidate != null && candidate.committedBet >= table.currentBet;
        });
      }

      publishSnapshot(table);
    }

    table.currentPlayerId = null;
    appendAction(table, "Round " + roundType + " completed");
    publishSnapshot(table);
  }

  private void revealCommunityCards(RuntimeTable table, RoundType roundType, int cardsToReveal) {
    if (table.deck.isEmpty()) {
      throw new IllegalStateException("Deck exhausted while revealing community cards");
    }

    burnCard(table);
    for (int i = 0; i < cardsToReveal; i++) {
      table.communityCards.add(deckService.dealCard(table.deck));
    }

    table.roundType = roundType;
    CommunityCardsUpdatedMessage message = new CommunityCardsUpdatedMessage(
        MessageType.COMMUNITY_CARDS_UPDATED,
        table.tableId,
        table.handNumber,
        roundType,
        table.communityCards
    );
    outboundChannel.broadcastCommunityCardsUpdated(message);

    appendAction(table, roundType + " revealed: " + String.join(" ", table.communityCards));
    publishSnapshot(table);
  }

  private void resolveHandInternal(RuntimeTable table) {
    if (table.pot <= 0) {
      return;
    }

    List<RuntimePlayer> remainingPlayers = activePlayersInHand(table);
    if (remainingPlayers.isEmpty()) {
      return;
    }

    List<String> winnerIds;
    String handCategory;

    if (remainingPlayers.size() == 1) {
      RuntimePlayer soleWinner = remainingPlayers.getFirst();
      winnerIds = List.of(soleWinner.playerId);
      handCategory = "UNCONTESTED";
    } else {
      Map<String, List<String>> holeCardsByPlayer = new LinkedHashMap<>();
      for (RuntimePlayer player : remainingPlayers) {
        holeCardsByPlayer.put(player.playerId, player.holeCards);
      }
      PokerEngineAdapter.ShowdownResult showdown = pokerEngineAdapter.resolveWinners(holeCardsByPlayer, table.communityCards);
      winnerIds = showdown.winnerIds();
      handCategory = showdown.handCategory();
    }

    Map<String, Integer> payouts = pokerEngineAdapter.distributePot(winnerIds, table.pot);
    for (Map.Entry<String, Integer> payout : payouts.entrySet()) {
      RuntimePlayer winner = table.players.get(payout.getKey());
      if (winner != null) {
        winner.stack += payout.getValue();
      }
    }
    for (RuntimePlayer player : table.players.values()) {
      player.lastHandDelta = player.stack - player.handStartStack;
    }

    Map<String, Integer> updatedStacks = stackSnapshot(table);

    outboundChannel.broadcastHandResult(
        new HandResultMessage(
            MessageType.HAND_RESULT,
            table.tableId,
            table.handNumber,
            winnerIds,
            handCategory,
            table.pot,
            payouts,
            updatedStacks
        )
    );

    appendAction(table, "Hand " + table.handNumber + " settled. Winners: " + String.join(", ", winnerIds) + " (" + handCategory + ")");

    table.pot = 0;
    table.currentBet = 0;
    for (RuntimePlayer player : table.players.values()) {
      player.committedBet = 0;
      if (player.status == PlayerStatus.FOLDED && player.stack > 0) {
        player.status = PlayerStatus.ACTIVE;
      }
      if (player.status == PlayerStatus.ALL_IN && player.stack > 0) {
        player.status = PlayerStatus.ACTIVE;
      }
    }

    publishSnapshot(table);
  }

  private void eliminatePlayersInternal(RuntimeTable table) {
    for (RuntimePlayer player : table.players.values()) {
      if (player.stack <= 0 && player.status != PlayerStatus.ELIMINATED) {
        player.status = PlayerStatus.ELIMINATED;
        outboundChannel.broadcastPlayerEliminated(
            new PlayerEliminatedMessage(MessageType.PLAYER_ELIMINATED, table.tableId, player.playerId)
        );
        appendAction(table, player.playerId + " eliminated");
      }
    }

    publishSnapshot(table);
  }

  private void finishGameInternal(RuntimeTable table) {
    if (table.status == GameStatus.FINISHED) {
      return;
    }

    table.status = GameStatus.FINISHED;
    table.roundType = RoundType.SHOWDOWN;
    table.currentPlayerId = null;

    String winnerId = determineWinner(table);
    if (winnerId != null) {
      outboundChannel.broadcastGameFinished(
          new GameFinishedMessage(
              MessageType.GAME_FINISHED,
              table.tableId,
              winnerId,
              stackSnapshot(table),
              table.handNumber
          )
      );
      appendAction(table, "Game finished. Winner: " + winnerId);
      outboundChannel.closeSession("winner " + winnerId + " declared");
    } else {
      appendAction(table, "Game finished without a winner");
      outboundChannel.closeSession("game finished without winner");
    }

    publishSnapshot(table);
  }

  private PlayerAction normalizeAction(
      RuntimeTable table,
      RuntimePlayer player,
      PlayerAction proposed,
      List<ActionType> legalActions
  ) {
    int toCall = Math.max(0, table.currentBet - player.committedBet);

    if (proposed == null || proposed.action() == null) {
      return fallbackAction(toCall);
    }

    ActionType actionType = proposed.action();
    if (!legalActions.contains(actionType)) {
      return fallbackAction(toCall);
    }

    return switch (actionType) {
      case FOLD -> new PlayerAction(ActionType.FOLD, 0, reasonOrFallback(proposed.reason(), "fallback fold"));
      case CHECK -> toCall == 0
          ? new PlayerAction(ActionType.CHECK, 0, proposed.reason())
          : fallbackAction(toCall);
      case CALL -> {
        if (toCall == 0) {
          yield new PlayerAction(ActionType.CHECK, 0, reasonOrFallback(proposed.reason(), "converted check"));
        }
        int amount = Math.min(toCall, player.stack);
        yield new PlayerAction(ActionType.CALL, amount, proposed.reason());
      }
      case BET -> {
        if (table.currentBet != 0) {
          yield fallbackAction(toCall);
        }
        int target = Math.max(proposed.amount(), table.minRaise);
        int maxTarget = player.committedBet + player.stack;
        if (target > maxTarget) {
          target = maxTarget;
        }
        if (target <= player.committedBet) {
          yield fallbackAction(toCall);
        }
        yield new PlayerAction(ActionType.BET, target, proposed.reason());
      }
      case RAISE -> {
        if (table.currentBet == 0) {
          yield fallbackAction(toCall);
        }
        int minTarget = table.currentBet + table.minRaise;
        int target = Math.max(proposed.amount(), minTarget);
        int maxTarget = player.committedBet + player.stack;
        if (target > maxTarget) {
          target = maxTarget;
        }
        if (target <= table.currentBet) {
          int amount = Math.min(toCall, player.stack);
          yield amount > 0
              ? new PlayerAction(ActionType.CALL, amount, "raise converted to call")
              : fallbackAction(toCall);
        }
        yield new PlayerAction(ActionType.RAISE, target, proposed.reason());
      }
    };
  }

  private PlayerAction fallbackAction(int toCall) {
    if (toCall > 0) {
      return new PlayerAction(ActionType.FOLD, 0, "invalid response fallback");
    }
    return new PlayerAction(ActionType.CHECK, 0, "invalid response fallback");
  }

  private List<ActionType> legalActions(RuntimeTable table, RuntimePlayer player) {
    List<ActionType> actions = new ArrayList<>();
    int toCall = Math.max(0, table.currentBet - player.committedBet);

    if (toCall > 0) {
      actions.add(ActionType.FOLD);
      if (player.stack > 0) {
        actions.add(ActionType.CALL);
      }
      if (player.stack + player.committedBet > table.currentBet) {
        actions.add(ActionType.RAISE);
      }
    } else {
      actions.add(ActionType.CHECK);
      if (player.stack > 0) {
        actions.add(ActionType.BET);
      }
    }

    return actions;
  }

  private void applyAction(RuntimeTable table, RuntimePlayer player, PlayerAction action) {
    Objects.requireNonNull(action, "action must not be null");

    switch (action.action()) {
      case FOLD -> player.status = PlayerStatus.FOLDED;
      case CHECK -> {
        // no-op
      }
      case CALL -> {
        int contribution = Math.min(action.amount(), player.stack);
        contribute(table, player, contribution);
      }
      case BET, RAISE -> {
        int target = action.amount();
        int contribution = Math.max(0, target - player.committedBet);
        contribution = Math.min(contribution, player.stack);
        contribute(table, player, contribution);
        table.currentBet = Math.max(table.currentBet, player.committedBet);
      }
    }

    if (player.status != PlayerStatus.FOLDED && player.stack == 0) {
      player.status = PlayerStatus.ALL_IN;
    }
    if (player.status == PlayerStatus.ACTIVE && player.stack > 0) {
      // keep active
    }

    player.lastAction = action;

    appendAction(table, formatActionLog(table, player, action));
  }

  private void contribute(RuntimeTable table, RuntimePlayer player, int contribution) {
    if (contribution <= 0) {
      return;
    }

    player.stack -= contribution;
    player.committedBet += contribution;
    table.pot += contribution;

    if (player.committedBet > table.currentBet) {
      table.currentBet = player.committedBet;
    }
  }

  private String formatActionLog(RuntimeTable table, RuntimePlayer player, PlayerAction action) {
    return "Hand " + table.handNumber + " " + table.roundType + " " + player.playerId + " -> " + action.action()
        + (action.amount() > 0 ? " " + action.amount() : "");
  }

  private void postBlind(RuntimeTable table, RuntimePlayer player, int requestedBlind, String blindName) {
    if (player == null) {
      throw new IllegalStateException("Blind seat is empty");
    }

    int contribution = Math.min(requestedBlind, player.stack);
    contribute(table, player, contribution);
    player.lastAction = new PlayerAction(ActionType.BET, player.committedBet, blindName);
    if (player.stack == 0) {
      player.status = PlayerStatus.ALL_IN;
    }

    appendAction(table, player.playerId + " posted " + blindName + " " + contribution);
  }

  private void collectAntes(RuntimeTable table) {
    int ante = Math.max(0, properties.getAnte());
    if (ante == 0) {
      return;
    }

    for (RuntimePlayer player : orderedPlayers(table)) {
      if (!player.joined || player.status != PlayerStatus.ACTIVE || player.stack <= 0) {
        continue;
      }

      int contribution = Math.min(ante, player.stack);
      if (contribution <= 0) {
        continue;
      }

      player.stack -= contribution;
      table.pot += contribution;
      player.lastAction = new PlayerAction(ActionType.BET, contribution, "ante");
      if (player.stack == 0) {
        player.status = PlayerStatus.ALL_IN;
      }

      appendAction(table, player.playerId + " posted ante " + contribution);
    }
  }

  private void burnCard(RuntimeTable table) {
    if (!table.deck.isEmpty()) {
      table.deck.removeFirst();
    }
  }

  private void pauseForSpectators() {
    int delayMillis = Math.max(0, properties.getSpectatorDelayMillis());
    if (delayMillis == 0) {
      return;
    }
    try {
      Thread.sleep(delayMillis);
    } catch (InterruptedException interrupted) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("Dealer loop interrupted during spectator delay", interrupted);
    }
  }

  private boolean allBetsMatched(RuntimeTable table) {
    List<RuntimePlayer> players = activePlayersInHand(table);
    if (players.size() <= 1) {
      return true;
    }

    for (RuntimePlayer player : players) {
      if (player.status == PlayerStatus.ACTIVE && player.committedBet != table.currentBet) {
        return false;
      }
    }
    return true;
  }

  private boolean isGameOver(RuntimeTable table) {
    return eligiblePlayers(table).size() <= 1;
  }

  private String determineWinner(RuntimeTable table) {
    return table.players.values().stream()
        .filter(player -> player.joined)
        .max(Comparator.comparingInt((RuntimePlayer p) -> p.stack).thenComparingInt(p -> -p.seatNumber))
        .map(player -> player.playerId)
        .orElse(null);
  }

  private Map<String, Integer> stackSnapshot(RuntimeTable table) {
    return orderedPlayers(table).stream()
        .collect(Collectors.toMap(
            player -> player.playerId,
            player -> player.stack,
            (left, right) -> right,
            LinkedHashMap::new
        ));
  }

  private List<RuntimePlayer> eligiblePlayers(RuntimeTable table) {
    return orderedPlayers(table).stream()
        .filter(player -> player.joined)
        .filter(player -> player.status != PlayerStatus.ELIMINATED)
        .filter(player -> player.stack > 0)
        .toList();
  }

  private List<RuntimePlayer> activePlayersInHand(RuntimeTable table) {
    return orderedPlayers(table).stream().filter(this::isInCurrentHand).toList();
  }

  private boolean isInCurrentHand(RuntimePlayer player) {
    return player.joined && player.status != PlayerStatus.FOLDED && player.status != PlayerStatus.ELIMINATED;
  }

  private boolean canAct(RuntimePlayer player) {
    return isInCurrentHand(player) && player.status == PlayerStatus.ACTIVE && player.stack > 0;
  }

  private RuntimePlayer playerAtSeat(RuntimeTable table, int seatNumber) {
    if (seatNumber <= 0) {
      return null;
    }

    for (RuntimePlayer player : table.players.values()) {
      if (player.seatNumber == seatNumber) {
        return player;
      }
    }
    return null;
  }

  private int nextActiveSeat(RuntimeTable table, int fromSeat) {
    int seatCount = Math.max(table.players.size(), 1);
    int start = Math.max(fromSeat, 0);

    for (int offset = 1; offset <= seatCount; offset++) {
      int candidateSeat = ((start + offset - 1) % seatCount) + 1;
      RuntimePlayer player = playerAtSeat(table, candidateSeat);
      if (player != null && player.joined && player.status != PlayerStatus.ELIMINATED && player.stack > 0) {
        return candidateSeat;
      }
    }

    return 1;
  }

  private List<RuntimePlayer> orderedPlayers(RuntimeTable table) {
    return table.players.values().stream()
        .sorted(Comparator.comparingInt(player -> player.seatNumber))
        .toList();
  }

  private List<RuntimePlayer> orderedPlayersFromSeat(RuntimeTable table, int startSeat) {
    List<RuntimePlayer> ordered = orderedPlayers(table);
    if (ordered.isEmpty()) {
      return ordered;
    }

    int index = 0;
    for (int i = 0; i < ordered.size(); i++) {
      if (ordered.get(i).seatNumber == startSeat) {
        index = i;
        break;
      }
    }

    List<RuntimePlayer> rotated = new ArrayList<>(ordered.size());
    for (int i = 0; i < ordered.size(); i++) {
      rotated.add(ordered.get((index + i) % ordered.size()));
    }
    return rotated;
  }

  private List<RuntimePlayer> playersAfter(List<RuntimePlayer> order, String playerId) {
    int index = 0;
    for (int i = 0; i < order.size(); i++) {
      if (Objects.equals(order.get(i).playerId, playerId)) {
        index = i;
        break;
      }
    }

    List<RuntimePlayer> result = new ArrayList<>(order.size() - 1);
    for (int i = 1; i < order.size(); i++) {
      result.add(order.get((index + i) % order.size()));
    }
    return result;
  }

  private List<RuntimePlayer> currentHandOrder(RuntimeTable table) {
    if (table.currentHandOrderPlayerIds.isEmpty()) {
      return orderedPlayersFromSeat(table, table.dealerButtonSeat).stream()
          .filter(this::isInCurrentHand)
          .toList();
    }

    List<RuntimePlayer> ordered = new ArrayList<>(table.currentHandOrderPlayerIds.size());
    for (String playerId : table.currentHandOrderPlayerIds) {
      RuntimePlayer player = table.players.get(playerId);
      if (player != null && isInCurrentHand(player)) {
        ordered.add(player);
      }
    }
    return ordered;
  }

  private String first(Set<String> values) {
    return values.stream().findFirst().orElseThrow();
  }

  private List<String> configuredPlayerIds() {
    if ("UCW".equalsIgnoreCase(properties.getTransportMode()) && properties.getPlayerUcw() != null && !properties.getPlayerUcw().isEmpty()) {
      return new ArrayList<>(properties.getPlayerUcw().keySet());
    }
    if ("ACP".equalsIgnoreCase(properties.getTransportMode())
        && properties.getPlayerAgentIds() != null
        && !properties.getPlayerAgentIds().isEmpty()) {
      return new ArrayList<>(properties.getPlayerAgentIds().keySet());
    }
    return new ArrayList<>(properties.getPlayerEndpoints().keySet());
  }

  private void appendAction(RuntimeTable table, String message) {
    appendCapped(table.actionLog, Instant.now() + " " + message);
  }

  private void appendReasoning(RuntimeTable table, String reasoning) {
    appendCapped(table.reasoningLog, Instant.now() + " " + reasoning);
  }

  private void appendCapped(List<String> target, String value) {
    target.add(value);
    int max = 400;
    if (target.size() > max) {
      target.removeFirst();
    }
  }

  private String reasonOrFallback(String reason, String fallback) {
    return Optional.ofNullable(reason).filter(r -> !r.isBlank()).orElse(fallback);
  }

  private void publishSnapshot(RuntimeTable table) {
    repository.save(toTableState(table));
  }

  private TableState toTableState(RuntimeTable table) {
    List<SeatState> seats = orderedPlayers(table).stream()
        .map(player -> new SeatState(player.seatNumber, player.playerId, player.joined))
        .toList();

    Map<String, PlayerState> playerStates = orderedPlayers(table).stream()
        .collect(Collectors.toMap(
            player -> player.playerId,
            player -> new PlayerState(
                player.playerId,
                player.stack,
                player.status,
                properties.isDemoVisibilityMode() ? player.holeCards : List.of(),
                player.committedBet,
                player.lastHandDelta,
                player.stack - player.startingStack,
                player.lastAction
            ),
            (left, right) -> right,
            LinkedHashMap::new
        ));

    GameState gameState = new GameState(
        table.tableId,
        table.handNumber,
        table.roundType,
        table.communityCards,
        playerStates,
        table.pot,
        table.currentBet,
        table.minRaise,
        table.currentPlayerId,
        table.status
    );

    return new TableState(table.tableId, table.status, seats, gameState, table.actionLog, table.reasoningLog);
  }

  private GameState toGameState(RuntimeTable table) {
    return toTableState(table).gameState();
  }

  private GameState toPlayerGameState(RuntimeTable table, String viewerPlayerId) {
    Map<String, PlayerState> playerStates = orderedPlayers(table).stream()
        .collect(Collectors.toMap(
            player -> player.playerId,
            player -> new PlayerState(
                player.playerId,
                player.stack,
                player.status,
                Objects.equals(player.playerId, viewerPlayerId) ? List.copyOf(player.holeCards) : List.of(),
                player.committedBet,
                player.lastHandDelta,
                player.stack - player.startingStack,
                player.lastAction
            ),
            (left, right) -> right,
            LinkedHashMap::new
        ));

    return new GameState(
        table.tableId,
        table.handNumber,
        table.roundType,
        table.communityCards,
        playerStates,
        table.pot,
        table.currentBet,
        table.minRaise,
        table.currentPlayerId,
        table.status
    );
  }

  private static final class RuntimeTable {
    private final String tableId;
    private final Map<String, RuntimePlayer> players = new LinkedHashMap<>();
    private final List<String> communityCards = new ArrayList<>();
    private final Deque<String> deck = new ArrayDeque<>();
    private final List<String> actionLog = new ArrayList<>();
    private final List<String> reasoningLog = new ArrayList<>();
    private final List<String> currentHandOrderPlayerIds = new ArrayList<>();

    private GameStatus status = GameStatus.WAITING_FOR_PLAYERS;
    private RoundType roundType = RoundType.PRE_FLOP;
    private int handNumber = 0;
    private int dealerButtonSeat = 0;
    private int smallBlindSeat = 0;
    private int bigBlindSeat = 0;
    private int pot = 0;
    private int currentBet = 0;
    private int minRaise;
    private String currentPlayerId;

    private RuntimeTable(String tableId, int minRaise) {
      this.tableId = tableId;
      this.minRaise = minRaise;
    }
  }

  private static final class RuntimePlayer {
    private final String playerId;
    private final int seatNumber;
    private final List<String> holeCards = new ArrayList<>(2);
    private final int startingStack;

    private int stack;
    private int committedBet;
    private int handStartStack;
    private int lastHandDelta;
    private boolean joined;
    private PlayerStatus status;
    private PlayerAction lastAction;

    private RuntimePlayer(String playerId, int seatNumber, int startingStack) {
      this.playerId = playerId;
      this.seatNumber = seatNumber;
      this.startingStack = startingStack;
      this.stack = startingStack;
      this.handStartStack = startingStack;
      this.status = PlayerStatus.WAITING;
    }
  }
}
