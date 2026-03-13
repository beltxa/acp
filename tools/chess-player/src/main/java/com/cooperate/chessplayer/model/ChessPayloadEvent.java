package com.cooperate.chessplayer.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class ChessPayloadEvent {
  @JsonProperty("profile")
  public String profile;
  @JsonProperty("match_id")
  public UUID matchId;
  @JsonProperty("game_id")
  public UUID gameId;
  @JsonProperty("sequence")
  public Integer sequence;
  @JsonProperty("event_type")
  public String eventType;
  @JsonProperty("side_to_move")
  public String sideToMove;
  @JsonProperty("move")
  public MoveData move;
  @JsonProperty("fen_after")
  public String fenAfter;
  @JsonProperty("game_status")
  public String gameStatus;
  @JsonProperty("result")
  public String result;
  @JsonProperty("winner_participant_urn")
  public String winnerParticipantUrn;
  @JsonProperty("reason")
  public String reason;
  @JsonProperty("sent_at")
  public Instant sentAt;

  @JsonInclude(JsonInclude.Include.NON_NULL)
  public static class MoveData {
    @JsonProperty("uci")
    public String uci;
    @JsonProperty("san")
    public String san;
  }
}
