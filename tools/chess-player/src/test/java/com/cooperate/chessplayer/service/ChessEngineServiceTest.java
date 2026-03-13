package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.GameOutcome;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class ChessEngineServiceTest {

  private final ChessEngineService engine = new ChessEngineService();

  @Test
  void shouldGenerateLegalOpeningMove() {
    var decision = engine.nextMove(engine.initialFen(), ChessColor.WHITE);
    assertNotNull(decision.uci());
    assertEquals(4, decision.uci().length());
    assertNotNull(decision.fenAfter());
  }

  @Test
  void shouldDetectOngoingInitialPosition() {
    var assessment = engine.assess(engine.initialFen(), 0, 100);
    assertEquals(GameOutcome.ONGOING, assessment.outcome());
  }
}
