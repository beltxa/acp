package com.cooperate.poker.dealer.service;

import com.cooperate.poker.common.model.TableState;

public interface DealerService {
  void startGame();

  void resetGame();

  void startHand();

  void runBettingRound();

  void resolveHand();

  void eliminatePlayers();

  void finishGame();

  TableState getCurrentTableState();

  boolean isRunning();
}
