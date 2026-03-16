from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import chess
import pytest

from app.config import AppConfig
from app.engine import ChessEngineService
from app.models import (
    ChessColor,
    GameOutcome,
    MatchStateStatus,
    PlayerRole,
    ReasoningEffort,
)
from app.orchestrator import ChessMatchOrchestrator
from app.payload_codec import ChessPayloadCodec
from app.pgn_exporter import PgnExporter
from app.state_store import MatchStateStore


class FakeAcpChessClient:
    def __init__(self, send_ok: bool = True) -> None:
        self.send_ok = send_ok
        self.sent_events = []

    def send_chess_event(self, event) -> bool:  # noqa: ANN001
        self.sent_events.append(event)
        return self.send_ok


@pytest.fixture()
def payload_codec() -> ChessPayloadCodec:
    return ChessPayloadCodec()


def _build_config(tmp_path: Path, *, color: ChessColor, max_plies: int = 160) -> AppConfig:
    return AppConfig(
        server_port=8088,
        role=PlayerRole.INITIATOR,
        color=color,
        local_agent_id="agent:player1@localhost:8088",
        remote_agent_id="agent:player2@localhost:8089",
        local_display_name="Player 1 AI",
        remote_display_name="Player 2 AI",
        public_base_url="http://localhost:8088",
        acp_message_path="/api/v1/acp/messages",
        acp_storage_dir=str(tmp_path / "acp"),
        acp_discovery_scheme="http",
        acp_relay_url=None,
        acp_allow_insecure_http=True,
        acp_allow_insecure_tls=False,
        acp_ca_file=None,
        acp_delivery_mode="direct",
        poll_interval_ms=2000,
        move_send_delay_ms=0,
        match_timeout_seconds=1800,
        max_plies=max_plies,
        pgn_export_enabled=False,
        pgn_export_dir=str(tmp_path / "pgn"),
        state_file=str(tmp_path / "state" / "matches.json"),
        reduced_motion="reduced",
        reasoning_effort=ReasoningEffort.MEDIUM,
        openai_api_key=None,
        openai_model="o3-mini",
    )


def _build_orchestrator(
    tmp_path: Path,
    *,
    local_color: ChessColor,
    send_ok: bool = True,
    max_plies: int = 160,
) -> tuple[ChessMatchOrchestrator, FakeAcpChessClient]:
    config = _build_config(tmp_path, color=local_color, max_plies=max_plies)
    acp_client = FakeAcpChessClient(send_ok=send_ok)
    engine = ChessEngineService()
    store = MatchStateStore(config)
    orchestrator = ChessMatchOrchestrator(
        config=config,
        acp_client=acp_client,  # type: ignore[arg-type]
        chess_engine_service=engine,
        payload_codec=ChessPayloadCodec(),
        match_state_store=store,
        pgn_exporter=PgnExporter(config),
    )
    return orchestrator, acp_client


def _fen_after_move(uci_move: str) -> str:
    board = chess.Board()
    board.push(chess.Move.from_uci(uci_move))
    return board.fen(en_passant="fen")


def test_should_create_and_update_state_from_inbound_move_payload(tmp_path: Path, payload_codec: ChessPayloadCodec) -> None:
    orchestrator, _ = _build_orchestrator(tmp_path, local_color=ChessColor.BLACK)
    match_id = uuid4()
    payload = payload_codec.to_move_payload(match_id, 1, ChessColor.BLACK, "e2e4", _fen_after_move("e2e4"))

    orchestrator.on_inbound_payload(payload)

    state = orchestrator.find_match(match_id)
    assert state is not None
    assert state.matchId == match_id
    assert state.latestSequence == 1
    assert state.moveHistoryUci[0] == "e2e4"
    assert state.status is MatchStateStatus.ACTIVE


def test_should_send_move_when_it_is_local_turn(tmp_path: Path) -> None:
    orchestrator, acp_client = _build_orchestrator(tmp_path, local_color=ChessColor.WHITE, send_ok=True)
    started = orchestrator.start_match()

    orchestrator.poll()

    updated = orchestrator.find_match(UUID(str(started.ucwId)))
    assert updated is not None
    assert updated.latestSequence >= 1
    assert len(updated.moveHistoryUci) >= 1
    assert updated.status is MatchStateStatus.ACTIVE
    assert len(acp_client.sent_events) == 1


def test_should_send_terminal_event_and_complete_when_game_becomes_terminal(tmp_path: Path) -> None:
    orchestrator, acp_client = _build_orchestrator(
        tmp_path,
        local_color=ChessColor.WHITE,
        send_ok=True,
        max_plies=0,
    )
    started = orchestrator.start_match()

    orchestrator.poll()

    updated = orchestrator.find_match(UUID(str(started.ucwId)))
    assert updated is not None
    assert updated.outcome is GameOutcome.DRAW
    assert updated.status is MatchStateStatus.COMPLETED
    assert updated.completionProposalSent is True
    assert len(acp_client.sent_events) == 1


def test_should_reject_reasoning_effort_change_while_match_is_active(tmp_path: Path) -> None:
    orchestrator, _ = _build_orchestrator(tmp_path, local_color=ChessColor.WHITE)
    orchestrator.start_match()

    with pytest.raises(RuntimeError):
        orchestrator.set_next_reasoning_effort(ReasoningEffort.HIGH)
