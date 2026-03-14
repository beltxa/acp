from __future__ import annotations

import logging
from pathlib import Path

import chess
import chess.pgn

from .config import AppConfig
from .models import GameOutcome, MatchState


LOG = logging.getLogger(__name__)


class PgnExporter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def export(self, state: MatchState | None) -> None:
        if (
            state is None
            or state.matchId is None
            or not self._config.pgn_export_enabled
        ):
            return

        output_dir = Path(self._config.pgn_export_dir)
        output_path = output_dir / f"{state.matchId}.pgn"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self._build_pgn(state), encoding="utf-8")
            LOG.info("Exported PGN for match %s to %s", state.matchId, output_path)
        except Exception:
            LOG.warning("Failed to export PGN for match %s", state.matchId, exc_info=True)

    @staticmethod
    def _build_pgn(state: MatchState) -> str:
        board = chess.Board()
        game = chess.pgn.Game()
        game.headers["Event"] = "ACP Chess AI Match"
        game.headers["Site"] = "ACP Direct"
        game.headers["Round"] = "-"
        game.headers["White"] = "AI-White"
        game.headers["Black"] = "AI-Black"
        game.headers["Result"] = PgnExporter._result_token(state.outcome)
        game.headers["MatchId"] = str(state.matchId)
        game.headers["SessionId"] = str(state.ucwId)

        node = game
        for uci in state.moveHistoryUci or []:
            if not uci or len(uci) < 4:
                break
            try:
                move = chess.Move.from_uci(uci)
            except ValueError:
                break
            if move not in board.legal_moves:
                break
            node = node.add_variation(move)
            board.push(move)

        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        return game.accept(exporter) + "\n"

    @staticmethod
    def _result_token(outcome: GameOutcome | None) -> str:
        if outcome is GameOutcome.WHITE_WIN:
            return "1-0"
        if outcome is GameOutcome.BLACK_WIN:
            return "0-1"
        if outcome is GameOutcome.DRAW:
            return "1/2-1/2"
        return "*"
