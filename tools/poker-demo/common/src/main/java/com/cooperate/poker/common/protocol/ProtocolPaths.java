package com.cooperate.poker.common.protocol;

public final class ProtocolPaths {
  private ProtocolPaths() {
  }

  public static final String PLAYER_BASE = "/api/player";
  public static final String INVITATION = PLAYER_BASE + "/invitation";
  public static final String HAND_START = PLAYER_BASE + "/hand-start";
  public static final String HOLE_CARDS = PLAYER_BASE + "/hole-cards";
  public static final String ACTION_REQUEST = PLAYER_BASE + "/action-request";
  public static final String ACTION_APPLIED = PLAYER_BASE + "/action-applied";
  public static final String COMMUNITY_CARDS_UPDATED = PLAYER_BASE + "/community-cards";
  public static final String HAND_RESULT = PLAYER_BASE + "/hand-result";
  public static final String PLAYER_ELIMINATED = PLAYER_BASE + "/eliminated";
  public static final String GAME_FINISHED = PLAYER_BASE + "/game-finished";
}
