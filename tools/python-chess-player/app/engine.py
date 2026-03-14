from __future__ import annotations

import logging
import random
from dataclasses import dataclass

import chess

from .models import ChessColor, GameOutcome, ReasoningEffort
from .openai_client import OpenAiChessMoveClient


LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MoveDecision:
    uci: str
    next_to_move: ChessColor
    fen_after: str


@dataclass(frozen=True, slots=True)
class PositionAssessment:
    outcome: GameOutcome
    reason: str | None


class ChessEngineService:
    def __init__(self, openai_client: OpenAiChessMoveClient | None = None) -> None:
        self._openai_client = openai_client

    def initial_fen(self) -> str:
        return chess.Board().fen(en_passant="fen")

    def next_move(
        self,
        fen: str,
        side_to_play: ChessColor,
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
    ) -> MoveDecision:
        board = self.load_board(fen)
        current_side = ChessColor.from_turn(board.turn)
        if current_side != side_to_play:
            raise RuntimeError("board side to move does not match local player side")

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            raise RuntimeError("no legal moves available")

        chosen_move = self._select_move(
            board.fen(en_passant="fen"),
            side_to_play,
            legal_moves,
            reasoning_effort,
        )
        board.push(chosen_move)
        return MoveDecision(
            uci=chosen_move.uci(),
            next_to_move=ChessColor.from_turn(board.turn),
            fen_after=board.fen(en_passant="fen"),
        )

    def assess(self, fen: str, played_plies: int, max_plies: int) -> PositionAssessment:
        board = self.load_board(fen)
        if board.is_checkmate():
            winner = ChessColor.from_turn(not board.turn)
            outcome = GameOutcome.WHITE_WIN if winner is ChessColor.WHITE else GameOutcome.BLACK_WIN
            return PositionAssessment(outcome=outcome, reason="CHECKMATE")

        if board.is_stalemate():
            return PositionAssessment(outcome=GameOutcome.DRAW, reason="STALEMATE")

        if (
            board.is_insufficient_material()
            or board.is_repetition(3)
            or board.can_claim_fifty_moves()
            or board.can_claim_threefold_repetition()
        ):
            return PositionAssessment(outcome=GameOutcome.DRAW, reason="DRAW_RULE")

        if played_plies >= max_plies:
            return PositionAssessment(outcome=GameOutcome.DRAW, reason="MAX_PLIES")

        return PositionAssessment(outcome=GameOutcome.ONGOING, reason=None)

    def load_board(self, fen: str | None) -> chess.Board:
        board = chess.Board()
        if fen is not None and fen.strip():
            board.set_fen(fen.strip())
        return board

    def _select_move(
        self,
        fen: str,
        side_to_play: ChessColor,
        legal_moves: list[chess.Move],
        reasoning_effort: ReasoningEffort,
    ) -> chess.Move:
        if self._openai_client is not None:
            legal_uci = [move.uci() for move in legal_moves]
            suggested = self._openai_client.choose_move(
                fen=fen,
                side_to_play=side_to_play,
                legal_moves_uci=legal_uci,
                reasoning_effort=reasoning_effort,
            )
            if suggested is not None:
                suggested = suggested.lower()
                for legal_move in legal_moves:
                    if legal_move.uci().lower() == suggested:
                        return legal_move
                LOG.debug("OpenAI suggested non-legal move %s", suggested)

        sorted_moves = sorted(legal_moves, key=lambda move: move.uci())
        return random.choice(sorted_moves)
