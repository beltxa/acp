package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.ChessPayloadEvent;
import com.cooperate.chessplayer.model.GameOutcome;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Component
public class ChessPayloadCodec {
  public static final String PROFILE = "ACP_CHESS_V1";
  public static final String EVENT_MOVE = "MOVE";
  public static final String EVENT_GAME_END = "GAME_END";
  public static final String STATUS_ONGOING = "ONGOING";
  public static final String STATUS_FINISHED = "FINISHED";

  private final ObjectMapper objectMapper;

  public ChessPayloadCodec(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper;
  }

  public Optional<ChessPayloadEvent> parse(String payload) {
    if (payload == null || payload.isBlank()) {
      return Optional.empty();
    }
    try {
      ChessPayloadEvent event = objectMapper.readValue(payload, ChessPayloadEvent.class);
      if (event == null || !PROFILE.equals(event.profile) || event.matchId == null || event.sequence == null || event.eventType == null) {
        return Optional.empty();
      }
      return Optional.of(event);
    } catch (Exception ignored) {
      return Optional.empty();
    }
  }

  public Optional<ChessPayloadEvent> parse(Map<String, Object> payload) {
    if (payload == null || payload.isEmpty()) {
      return Optional.empty();
    }
    try {
      ChessPayloadEvent event = objectMapper.convertValue(payload, ChessPayloadEvent.class);
      if (event == null || !PROFILE.equals(event.profile) || event.matchId == null || event.sequence == null || event.eventType == null) {
        return Optional.empty();
      }
      return Optional.of(event);
    } catch (Exception ignored) {
      return Optional.empty();
    }
  }

  public String toMovePayload(UUID matchId, int sequence, ChessColor nextToMove, String uci, String fenAfter) {
    ChessPayloadEvent event = new ChessPayloadEvent();
    event.profile = PROFILE;
    event.matchId = matchId;
    event.gameId = matchId;
    event.sequence = sequence;
    event.eventType = EVENT_MOVE;
    event.sideToMove = nextToMove.name();
    event.fenAfter = fenAfter;
    event.gameStatus = STATUS_ONGOING;
    event.sentAt = Instant.now();

    ChessPayloadEvent.MoveData moveData = new ChessPayloadEvent.MoveData();
    moveData.uci = uci;
    moveData.san = uci;
    event.move = moveData;

    return write(event);
  }

  public String toGameEndPayload(UUID matchId, int sequence, GameOutcome outcome, String reason, String winnerParticipantUrn, String fenAfter) {
    ChessPayloadEvent event = new ChessPayloadEvent();
    event.profile = PROFILE;
    event.matchId = matchId;
    event.gameId = matchId;
    event.sequence = sequence;
    event.eventType = EVENT_GAME_END;
    event.fenAfter = fenAfter;
    event.gameStatus = STATUS_FINISHED;
    event.result = switch (outcome) {
      case WHITE_WIN -> "WHITE_WIN";
      case BLACK_WIN -> "BLACK_WIN";
      case DRAW -> "DRAW";
      case ONGOING -> "DRAW";
    };
    event.reason = reason;
    event.winnerParticipantUrn = winnerParticipantUrn;
    event.sentAt = Instant.now();
    return write(event);
  }

  private String write(ChessPayloadEvent event) {
    try {
      return objectMapper.writeValueAsString(event);
    } catch (Exception e) {
      throw new IllegalStateException("Failed to serialize chess payload", e);
    }
  }
}
