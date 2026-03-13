package com.cooperate.chessplayer.model;

import com.github.bhlangonijr.chesslib.Side;

public enum ChessColor {
  WHITE,
  BLACK;

  public Side toSide() {
    return this == WHITE ? Side.WHITE : Side.BLACK;
  }

  public ChessColor opposite() {
    return this == WHITE ? BLACK : WHITE;
  }

  public static ChessColor fromSide(Side side) {
    return side == Side.BLACK ? BLACK : WHITE;
  }
}
