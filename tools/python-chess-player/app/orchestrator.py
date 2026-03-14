from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from uuid import UUID, uuid4

import chess

from .acp_client import AcpChessClient
from .config import AppConfig
from .engine import ChessEngineService
from .models import (
    ChessColor,
    ChessPayloadEvent,
    GameOutcome,
    MatchState,
    MatchStateStatus,
    ReasoningEffort,
    utc_now,
)
from .payload_codec import ChessPayloadCodec
from .pgn_exporter import PgnExporter
from .state_store import MatchStateStore


LOG = logging.getLogger(__name__)


class ChessMatchOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        acp_client: AcpChessClient,
        chess_engine_service: ChessEngineService,
        payload_codec: ChessPayloadCodec,
        match_state_store: MatchStateStore,
        pgn_exporter: PgnExporter,
    ) -> None:
        self._config = config
        self._acp_client = acp_client
        self._chess_engine_service = chess_engine_service
        self._payload_codec = payload_codec
        self._match_state_store = match_state_store
        self._pgn_exporter = pgn_exporter
        self._next_reasoning_effort = self._normalize_effort(config.reasoning_effort)
        self._lock = threading.RLock()

        LOG.info(
            "Chess player starting: role=%s color=%s localAgentId=%s remoteAgentId=%s endpoint=%s openaiModel=%s openaiKeyConfigured=%s reasoningEffort=%s",
            self._config.role.value,
            self._config.color.value,
            self._config.local_agent_id,
            self._config.remote_agent_id,
            self._config.resolve_acp_endpoint(),
            self._config.openai_model,
            bool(self._config.openai_api_key and self._config.openai_api_key.strip()),
            self._next_reasoning_effort.value,
        )

    def start_match(self, reasoning_effort: ReasoningEffort | None = None) -> MatchState:
        with self._lock:
            match_effort = self._normalize_effort(reasoning_effort or self._next_reasoning_effort)
            match_id = uuid4()
            now = utc_now()
            state = MatchState(
                ucwId=match_id,
                matchId=match_id,
                localColor=self._config.color,
                localParticipantUrn=self._config.local_agent_id,
                remoteParticipantUrn=self._config.remote_agent_id,
                localUserUrn=self._config.local_display_name,
                remoteUserUrn=self._config.remote_display_name,
                reasoningEffort=match_effort,
                currentFen=self._chess_engine_service.initial_fen(),
                ucwStatus="ACTIVE",
                status=MatchStateStatus.ACTIVE,
                outcome=GameOutcome.ONGOING,
                createdAt=now,
                updatedAt=now,
            )
            self._match_state_store.upsert(state)
            LOG.info("Started ACP chess match %s", match_id)
            return state

    def get_next_reasoning_effort(self) -> ReasoningEffort:
        with self._lock:
            return self._next_reasoning_effort

    def set_next_reasoning_effort(self, effort: ReasoningEffort | None) -> None:
        with self._lock:
            normalized = self._normalize_effort(effort)
            if self._has_in_progress_matches():
                raise RuntimeError("reasoning effort cannot change while a match is active")
            self._next_reasoning_effort = normalized
            self._config.reasoning_effort = normalized

    def list_matches(self) -> list[MatchState]:
        return self._match_state_store.list()

    def find_match(self, ucw_id: UUID) -> MatchState | None:
        return self._match_state_store.find(ucw_id)

    def on_inbound_payload(self, payload: dict[str, object] | None) -> None:
        with self._lock:
            event = self._payload_codec.parse(payload)
            if event is None:
                return
            state = self._find_or_create_state(event)
            self._apply_event(state, event)
            self._finalize_if_completed(state)
            self._match_state_store.upsert(state)

    def poll(self) -> None:
        with self._lock:
            try:
                for state in self._match_state_store.list():
                    self._process_match(state)
            except Exception:
                LOG.warning("Chess poll cycle failed", exc_info=True)

    def _process_match(self, state: MatchState) -> None:
        if state is None or state.ucwId is None:
            return

        if state.reasoningEffort is None:
            state.reasoningEffort = self._next_reasoning_effort
        if state.currentFen is None or not state.currentFen.strip():
            state.currentFen = self._chess_engine_service.initial_fen()
        if state.outcome is None:
            state.outcome = GameOutcome.ONGOING

        if state.outcome is GameOutcome.ONGOING:
            self._apply_timeout_policy(state)
            assessment = self._chess_engine_service.assess(
                state.currentFen,
                len(state.moveHistoryUci or []),
                self._config.max_plies,
            )
            if assessment.outcome.is_terminal():
                state.outcome = assessment.outcome
                state.outcomeReason = assessment.reason

        if state.outcome.is_terminal():
            self._send_game_end_if_needed(state)
            self._finalize_if_completed(state)
            self._match_state_store.upsert(state)
            return

        board = self._chess_engine_service.load_board(state.currentFen)
        side_to_move = ChessColor.from_turn(board.turn)
        if side_to_move is not state.localColor:
            state.status = MatchStateStatus.ACTIVE
            state.ucwStatus = "ACTIVE"
            self._match_state_store.upsert(state)
            return

        try:
            decision = self._chess_engine_service.next_move(
                state.currentFen,
                state.localColor,
                self._normalize_effort(state.reasoningEffort),
            )
        except Exception:
            LOG.warning("Unable to compute next move for match %s", state.matchId, exc_info=True)
            return

        if not self._wait_before_move_submit(state.matchId):
            return

        next_sequence = state.latestSequence + 1
        outbound = self._payload_codec.parse(
            self._payload_codec.to_move_payload(
                match_id=state.matchId,
                sequence=next_sequence,
                next_to_move=decision.next_to_move,
                uci=decision.uci,
                fen_after=decision.fen_after,
            )
        )
        if outbound is None:
            return
        if not self._acp_client.send_chess_event(outbound):
            return

        self._apply_event(state, outbound)
        assessment = self._chess_engine_service.assess(
            state.currentFen,
            len(state.moveHistoryUci or []),
            self._config.max_plies,
        )
        if assessment.outcome.is_terminal():
            state.outcome = assessment.outcome
            state.outcomeReason = assessment.reason
            self._send_game_end_if_needed(state)

        self._finalize_if_completed(state)
        self._match_state_store.upsert(state)

    def _find_or_create_state(self, event: ChessPayloadEvent) -> MatchState:
        for state in self._match_state_store.list():
            if state is not None and event.match_id is not None and event.match_id == state.matchId:
                return state

        match_id = event.match_id or uuid4()
        now = utc_now()
        return MatchState(
            ucwId=match_id,
            matchId=match_id,
            localColor=self._config.color,
            localParticipantUrn=self._config.local_agent_id,
            remoteParticipantUrn=self._config.remote_agent_id,
            localUserUrn=self._config.local_display_name,
            remoteUserUrn=self._config.remote_display_name,
            reasoningEffort=self._next_reasoning_effort,
            currentFen=self._chess_engine_service.initial_fen(),
            ucwStatus="ACTIVE",
            status=MatchStateStatus.ACTIVE,
            outcome=GameOutcome.ONGOING,
            createdAt=now,
            updatedAt=now,
        )

    def _apply_event(self, state: MatchState, event: ChessPayloadEvent) -> None:
        if (
            state is None
            or event is None
            or event.sequence is None
            or event.sequence <= state.latestSequence
        ):
            return

        if event.match_id is not None:
            state.matchId = event.match_id
            state.ucwId = event.match_id

        if state.currentFen is None or not state.currentFen.strip():
            state.currentFen = self._chess_engine_service.initial_fen()

        board = self._chess_engine_service.load_board(state.currentFen)

        if (
            event.event_type == ChessPayloadCodec.EVENT_MOVE
            and event.move is not None
            and event.move.uci is not None
        ):
            applied = self._apply_uci_move(board, event.move.uci)
            if not applied and event.fen_after and event.fen_after.strip():
                try:
                    board.set_fen(event.fen_after)
                    applied = True
                except ValueError:
                    applied = False
            if not applied:
                LOG.warning("Unable to apply inbound move %s for match %s", event.move.uci, state.matchId)
                return

            moves = list(state.moveHistoryUci or [])
            moves.append(event.move.uci)
            state.moveHistoryUci = moves
            state.currentFen = board.fen(en_passant="fen")
            state.latestSequence = event.sequence
            state.lastActionAt = utc_now()
            state.status = MatchStateStatus.ACTIVE
            state.ucwStatus = "ACTIVE"
            return

        if event.event_type == ChessPayloadCodec.EVENT_GAME_END:
            if event.fen_after and event.fen_after.strip():
                try:
                    board.set_fen(event.fen_after)
                except ValueError:
                    LOG.debug("Invalid fen_after in GAME_END event", exc_info=True)
            state.currentFen = board.fen(en_passant="fen")
            state.latestSequence = event.sequence
            if event.result is not None:
                state.outcome = self._parse_outcome(event.result)
            state.outcomeReason = event.reason
            state.status = MatchStateStatus.COMPLETED
            state.ucwStatus = "COMPLETED"
            state.completionProposalSent = True

    def _wait_before_move_submit(self, match_id: UUID) -> bool:
        delay_ms = max(0, self._config.move_send_delay_ms)
        if delay_ms <= 0:
            return True
        try:
            time.sleep(delay_ms / 1000.0)
            return True
        except Exception:
            LOG.warning("Interrupted while delaying move submission for match %s", match_id, exc_info=True)
            return False

    def _send_game_end_if_needed(self, state: MatchState) -> None:
        if (
            state is None
            or state.outcome is None
            or not state.outcome.is_terminal()
            or state.completionProposalSent
        ):
            return

        next_sequence = state.latestSequence + 1
        winner_agent_id = self._winner_agent_id(state)
        outbound = self._payload_codec.parse(
            self._payload_codec.to_game_end_payload(
                match_id=state.matchId,
                sequence=next_sequence,
                outcome=state.outcome,
                reason=state.outcomeReason,
                winner_participant_urn=winner_agent_id,
                fen_after=state.currentFen,
            )
        )
        if outbound is None:
            return
        if not self._acp_client.send_chess_event(outbound):
            state.status = MatchStateStatus.COMPLETING
            state.ucwStatus = "ACTIVE"
            return

        self._apply_event(state, outbound)
        state.completionProposalSent = True
        state.lastActionAt = utc_now()

    @staticmethod
    def _winner_agent_id(state: MatchState) -> str | None:
        if state.outcome is GameOutcome.WHITE_WIN:
            return (
                state.localParticipantUrn
                if state.localColor is ChessColor.WHITE
                else state.remoteParticipantUrn
            )
        if state.outcome is GameOutcome.BLACK_WIN:
            return (
                state.localParticipantUrn
                if state.localColor is ChessColor.BLACK
                else state.remoteParticipantUrn
            )
        return None

    def _apply_timeout_policy(self, state: MatchState) -> None:
        if state.createdAt is None or state.outcome.is_terminal():
            return
        elapsed = utc_now() - state.createdAt
        if elapsed >= timedelta(seconds=self._config.match_timeout_seconds):
            state.outcome = GameOutcome.DRAW
            state.outcomeReason = "TIMEOUT"

    def _finalize_if_completed(self, state: MatchState) -> None:
        if state.outcome is None or not state.outcome.is_terminal():
            state.status = MatchStateStatus.ACTIVE
            state.ucwStatus = "ACTIVE"
            return

        if state.completionProposalSent:
            state.status = MatchStateStatus.COMPLETED
            state.ucwStatus = "COMPLETED"
            if not state.pgnExported:
                self._pgn_exporter.export(state)
                state.pgnExported = True
            return

        state.status = MatchStateStatus.COMPLETING
        state.ucwStatus = "ACTIVE"

    @staticmethod
    def _apply_uci_move(board: chess.Board, uci: str) -> bool:
        if uci is None or len(uci) < 4:
            return False
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return False
        if move not in board.legal_moves:
            return False
        board.push(move)
        return True

    @staticmethod
    def _parse_outcome(value: str | None) -> GameOutcome:
        normalized = (value or "").strip().upper()
        if normalized == "WHITE_WIN":
            return GameOutcome.WHITE_WIN
        if normalized == "BLACK_WIN":
            return GameOutcome.BLACK_WIN
        if normalized in {"DRAW", "RESIGNATION"}:
            return GameOutcome.DRAW
        return GameOutcome.ONGOING

    def _has_in_progress_matches(self) -> bool:
        for state in self._match_state_store.list():
            if state is None:
                continue
            if state.status in {
                MatchStateStatus.ACTIVE,
                MatchStateStatus.INVITED,
                MatchStateStatus.COMPLETING,
            }:
                return True
            if (state.ucwStatus or "").upper() == "ACTIVE":
                return True
        return False

    @staticmethod
    def _normalize_effort(effort: ReasoningEffort | None) -> ReasoningEffort:
        return effort or ReasoningEffort.MEDIUM
