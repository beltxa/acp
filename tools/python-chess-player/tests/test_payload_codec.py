from __future__ import annotations

from uuid import uuid4

from app.models import ChessColor
from app.payload_codec import ChessPayloadCodec


def test_should_round_trip_move_payload() -> None:
    codec = ChessPayloadCodec()
    match_id = uuid4()
    payload = codec.to_move_payload(match_id, 1, ChessColor.BLACK, "e2e4", "fen")

    parsed = codec.parse(payload)
    assert parsed is not None
    assert parsed.profile == ChessPayloadCodec.PROFILE
    assert parsed.event_type == "MOVE"
    assert parsed.match_id == match_id
    assert parsed.sequence == 1
    assert parsed.move is not None
    assert parsed.move.uci == "e2e4"
