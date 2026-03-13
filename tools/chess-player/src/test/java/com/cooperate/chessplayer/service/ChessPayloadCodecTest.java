package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.model.ChessColor;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ChessPayloadCodecTest {

  private final ChessPayloadCodec codec = new ChessPayloadCodec(new ObjectMapper().registerModule(new JavaTimeModule()));

  @Test
  void shouldRoundTripMovePayload() {
    UUID matchId = UUID.randomUUID();
    String payload = codec.toMovePayload(matchId, 1, ChessColor.BLACK, "e2e4", "fen");

    var parsed = codec.parse(payload);
    assertTrue(parsed.isPresent());
    assertEquals(ChessPayloadCodec.PROFILE, parsed.get().profile);
    assertEquals("MOVE", parsed.get().eventType);
    assertEquals(matchId, parsed.get().matchId);
    assertEquals(1, parsed.get().sequence);
    assertEquals("e2e4", parsed.get().move.uci);
  }
}
