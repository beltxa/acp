from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .models import ChessColor, ChessMoveData, ChessPayloadEvent, GameOutcome


class ChessPayloadCodec:
    PROFILE = "ACP_CHESS_V1"
    EVENT_MOVE = "MOVE"
    EVENT_GAME_END = "GAME_END"
    STATUS_ONGOING = "ONGOING"
    STATUS_FINISHED = "FINISHED"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def parse(self, payload: dict[str, Any] | str | None) -> ChessPayloadEvent | None:
        if payload is None:
            return None
        try:
            if isinstance(payload, str):
                if not payload.strip():
                    return None
                raw = json.loads(payload)
            else:
                raw = payload
            event = ChessPayloadEvent.model_validate(raw)
            if (
                event.profile != self.PROFILE
                or event.match_id is None
                or event.sequence is None
                or event.event_type is None
            ):
                return None
            return event
        except Exception:
            return None

    def to_move_payload(
        self,
        match_id: UUID,
        sequence: int,
        next_to_move: ChessColor,
        uci: str,
        fen_after: str,
    ) -> dict[str, Any]:
        event = ChessPayloadEvent(
            profile=self.PROFILE,
            match_id=match_id,
            game_id=match_id,
            sequence=sequence,
            event_type=self.EVENT_MOVE,
            side_to_move=next_to_move.value,
            move=ChessMoveData(uci=uci, san=uci),
            fen_after=fen_after,
            game_status=self.STATUS_ONGOING,
            sent_at=self._now(),
        )
        return event.to_payload_dict()

    def to_game_end_payload(
        self,
        match_id: UUID,
        sequence: int,
        outcome: GameOutcome,
        reason: str | None,
        winner_participant_urn: str | None,
        fen_after: str,
    ) -> dict[str, Any]:
        result = {
            GameOutcome.WHITE_WIN: "WHITE_WIN",
            GameOutcome.BLACK_WIN: "BLACK_WIN",
            GameOutcome.DRAW: "DRAW",
            GameOutcome.ONGOING: "DRAW",
        }[outcome]
        event = ChessPayloadEvent(
            profile=self.PROFILE,
            match_id=match_id,
            game_id=match_id,
            sequence=sequence,
            event_type=self.EVENT_GAME_END,
            fen_after=fen_after,
            game_status=self.STATUS_FINISHED,
            result=result,
            reason=reason,
            winner_participant_urn=winner_participant_urn,
            sent_at=self._now(),
        )
        return event.to_payload_dict()

