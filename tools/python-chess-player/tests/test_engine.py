from __future__ import annotations

from app.engine import ChessEngineService
from app.models import ChessColor, GameOutcome


def test_should_generate_legal_opening_move() -> None:
    engine = ChessEngineService()
    decision = engine.next_move(engine.initial_fen(), ChessColor.WHITE)
    assert decision.uci is not None
    assert len(decision.uci) == 4
    assert decision.fen_after


def test_should_detect_ongoing_initial_position() -> None:
    engine = ChessEngineService()
    assessment = engine.assess(engine.initial_fen(), 0, 100)
    assert assessment.outcome is GameOutcome.ONGOING
