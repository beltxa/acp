from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .acp_client import AcpChessClient
from .config import AppConfig
from .engine import ChessEngineService
from .models import (
    MatchState,
    MatchStateStatus,
    ReasoningEffort,
    StartMatchRequest,
    StartMatchResponse,
)
from .openai_client import OpenAiChessMoveClient
from .orchestrator import ChessMatchOrchestrator
from .payload_codec import ChessPayloadCodec
from .pgn_exporter import PgnExporter
from .state_store import MatchStateStore


LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class AppContext:
    def __init__(self) -> None:
        self.config = AppConfig.from_env()
        self.config.ensure_paths()
        self.acp_client = AcpChessClient(self.config)
        self.payload_codec = ChessPayloadCodec()
        self.openai_client = OpenAiChessMoveClient(self.config)
        self.engine = ChessEngineService(self.openai_client)
        self.state_store = MatchStateStore(self.config)
        self.pgn_exporter = PgnExporter(self.config)
        self.orchestrator = ChessMatchOrchestrator(
            self.config,
            self.acp_client,
            self.engine,
            self.payload_codec,
            self.state_store,
            self.pgn_exporter,
        )
        self.poll_task: asyncio.Task[None] | None = None


ctx = AppContext()
app = FastAPI(title="ACP Python Chess Player")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _parse_agent_name(agent_id: str) -> str | None:
    if not isinstance(agent_id, str):
        return None
    normalized = agent_id.strip()
    if not normalized.startswith("agent:"):
        return None
    normalized = normalized[len("agent:") :]
    if "@" in normalized:
        normalized = normalized.split("@", 1)[0]
    return normalized or None


def _is_in_progress(state: MatchState) -> bool:
    if state.status in {MatchStateStatus.ACTIVE, MatchStateStatus.INVITED, MatchStateStatus.COMPLETING}:
        return True
    ucw_status = (state.ucwStatus or "").upper()
    return ucw_status in {"ACTIVE", "FROZEN", "COMPLETING", "PENDING", "INVITED_PENDING"}


async def _poll_loop() -> None:
    delay_seconds = max(0.25, ctx.config.poll_interval_ms / 1000.0)
    while True:
        try:
            await asyncio.to_thread(ctx.orchestrator.poll)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.warning("Polling loop failed", exc_info=True)
        await asyncio.sleep(delay_seconds)


@app.on_event("startup")
async def startup() -> None:
    if ctx.poll_task is None or ctx.poll_task.done():
        ctx.poll_task = asyncio.create_task(_poll_loop(), name="chess-poll-loop")


@app.on_event("shutdown")
async def shutdown() -> None:
    if ctx.poll_task is None:
        return
    ctx.poll_task.cancel()
    try:
        await ctx.poll_task
    except asyncio.CancelledError:
        pass
    ctx.poll_task = None


@app.get("/", response_class=HTMLResponse)
@app.get("/chess", response_class=HTMLResponse)
async def chess_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "local_agent_id": ctx.config.local_agent_id,
            "remote_agent_id": ctx.config.remote_agent_id,
            "local_display_name": ctx.config.local_display_name,
            "remote_display_name": ctx.config.remote_display_name,
            "default_color": ctx.config.color.value,
            "default_effort": ctx.orchestrator.get_next_reasoning_effort().api_value(),
        },
    )


@app.get("/api/v1/chess/config")
async def chess_config() -> dict[str, Any]:
    return {
        "local_agent_id": ctx.config.local_agent_id,
        "remote_agent_id": ctx.config.remote_agent_id,
        "local_display_name": ctx.config.local_display_name,
        "remote_display_name": ctx.config.remote_display_name,
        "default_color": ctx.config.color.value,
        "default_effort": ctx.orchestrator.get_next_reasoning_effort().api_value(),
        "poll_interval_ms": ctx.config.poll_interval_ms,
    }


@app.post("/api/v1/acp/messages")
async def receive_message(raw_message: dict[str, Any]) -> dict[str, Any]:
    result = ctx.acp_client.receive(raw_message)
    payload = result.get("decrypted_payload")
    if isinstance(payload, dict):
        await asyncio.to_thread(ctx.orchestrator.on_inbound_payload, payload)
    return result


@app.get("/.well-known/acp/agents/{name}")
async def identity_document(name: str) -> dict[str, Any]:
    local_name = _parse_agent_name(ctx.acp_client.get_local_agent_id())
    if local_name != name:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"identity_document": ctx.acp_client.get_identity_document()}


@app.get("/api/v1/acp/identity")
async def local_identity() -> dict[str, Any]:
    return {"identity_document": ctx.acp_client.get_identity_document()}


@app.post("/api/v1/chess/matches/start", response_model=StartMatchResponse, status_code=202)
async def start_match(request: StartMatchRequest | None = Body(default=None)) -> StartMatchResponse:
    try:
        effort = (
            ctx.orchestrator.get_next_reasoning_effort()
            if request is None
            else ReasoningEffort.from_value(request.reasoning_effort)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = await asyncio.to_thread(ctx.orchestrator.start_match, effort)
    return StartMatchResponse(
        match_id=state.matchId,
        session_id=state.ucwId,
        status=state.status.value,
        reasoning_effort=state.reasoningEffort.api_value() if state.reasoningEffort else None,
    )


@app.get("/api/v1/chess/matches", response_model=list[MatchState])
async def list_matches() -> list[MatchState]:
    return await asyncio.to_thread(ctx.orchestrator.list_matches)


@app.get("/api/v1/chess/matches/{match_id}", response_model=MatchState)
async def get_match(match_id: UUID) -> MatchState:
    state = await asyncio.to_thread(ctx.orchestrator.find_match, match_id)
    if state is None:
        raise HTTPException(status_code=404, detail="match not found")
    return state


@app.get("/api/v1/chess/matches/current")
async def current_match() -> dict[str, Any]:
    matches = await asyncio.to_thread(ctx.orchestrator.list_matches)
    if not matches:
        return {"match": None}
    for state in reversed(matches):
        if _is_in_progress(state):
            return {"match": state.model_dump(mode="json")}
    return {"match": matches[-1].model_dump(mode="json")}


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=AppConfig.from_env().server_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
