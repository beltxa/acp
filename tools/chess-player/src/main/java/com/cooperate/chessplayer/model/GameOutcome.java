package com.cooperate.chessplayer.model;

public enum GameOutcome {
  ONGOING,
  WHITE_WIN,
  BLACK_WIN,
  DRAW;

  public boolean isTerminal() {
    return this != ONGOING;
  }
}
