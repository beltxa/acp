from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChessColor(str, Enum):
    WHITE = "WHITE"
    BLACK = "BLACK"

    def opposite(self) -> "ChessColor":
        return ChessColor.BLACK if self is ChessColor.WHITE else ChessColor.WHITE

    @classmethod
    def from_turn(cls, is_white_turn: bool) -> "ChessColor":
        return cls.WHITE if is_white_turn else cls.BLACK


class PlayerRole(str, Enum):
    INITIATOR = "INITIATOR"
    RESPONDER = "RESPONDER"


class MatchStateStatus(str, Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GameOutcome(str, Enum):
    ONGOING = "ONGOING"
    WHITE_WIN = "WHITE_WIN"
    BLACK_WIN = "BLACK_WIN"
    DRAW = "DRAW"

    def is_terminal(self) -> bool:
        return self is not GameOutcome.ONGOING


class ReasoningEffort(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @classmethod
    def from_value(cls, value: str | None) -> "ReasoningEffort":
        if value is None or not value.strip():
            return cls.MEDIUM
        normalized = value.strip().upper()
        if normalized not in cls.__members__:
            raise ValueError(f"unsupported reasoning effort: {value}")
        return cls[normalized]

    def api_value(self) -> str:
        return self.value.lower()


class MatchState(BaseModel):
    model_config = ConfigDict(use_enum_values=False, populate_by_name=True)

    ucwId: UUID
    matchId: UUID
    localColor: ChessColor
    localParticipantUrn: str
    remoteParticipantUrn: str
    localUserUrn: str
    remoteUserUrn: str
    reasoningEffort: ReasoningEffort = ReasoningEffort.MEDIUM
    currentFen: str
    latestSequence: int = 0
    moveHistoryUci: list[str] = Field(default_factory=list)
    ucwStatus: str = "ACTIVE"
    status: MatchStateStatus = MatchStateStatus.INVITED
    outcome: GameOutcome = GameOutcome.ONGOING
    outcomeReason: str | None = None
    completionProposalSent: bool = False
    completionResponseSent: bool = False
    pgnExported: bool = False
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)
    lastActionAt: datetime | None = None


class ChessMoveData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    uci: str | None = None
    san: str | None = None


class ChessPayloadEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile: str | None = None
    match_id: UUID | None = Field(default=None, alias="match_id")
    game_id: UUID | None = Field(default=None, alias="game_id")
    sequence: int | None = None
    event_type: str | None = Field(default=None, alias="event_type")
    side_to_move: str | None = Field(default=None, alias="side_to_move")
    move: ChessMoveData | None = None
    fen_after: str | None = Field(default=None, alias="fen_after")
    game_status: str | None = Field(default=None, alias="game_status")
    result: str | None = None
    winner_participant_urn: str | None = Field(default=None, alias="winner_participant_urn")
    reason: str | None = None
    sent_at: datetime | None = Field(default=None, alias="sent_at")

    def to_payload_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class StartMatchRequest(BaseModel):
    reasoning_effort: str | None = None


class StartMatchResponse(BaseModel):
    match_id: UUID
    session_id: UUID
    status: str
    reasoning_effort: str | None = None


class StateEnvelope(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    matches: list[MatchState] = Field(default_factory=list)

