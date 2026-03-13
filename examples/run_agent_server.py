from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from fastapi import FastAPI, HTTPException
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "acp-sdk-python"))

from acp import Agent, FailReason, ProcessingError  # noqa: E402
from acp.messages import Envelope  # noqa: E402


def _agent_name(agent_id: str) -> str:
    body = agent_id.split("agent:", 1)[1]
    return body.split("@", 1)[0]


def create_handler(agent: Agent, always_fail: bool) -> Any:
    def _handler(payload: dict[str, Any], envelope: Envelope) -> dict[str, Any]:
        if always_fail:
            raise ProcessingError(
                reason_code=FailReason.POLICY_REJECTED,
                detail=f"{agent.agent_id} is configured to reject all messages",
            )

        force_fail_for = payload.get("force_fail_for", [])
        if isinstance(force_fail_for, list) and agent.agent_id in force_fail_for:
            raise ProcessingError(
                reason_code=FailReason.POLICY_REJECTED,
                detail=f"{agent.agent_id} rejected payload due to force_fail_for",
            )

        if envelope.message_class.value == "COMPENSATE":
            return {"compensated": True, "operation_id": envelope.operation_id}

        return {
            "accepted": True,
            "message_class": envelope.message_class.value,
            "payload_type": payload.get("type"),
        }

    return _handler


def build_app(agent: Agent, always_fail: bool) -> FastAPI:
    app = FastAPI(title=f"ACP Agent Node ({agent.agent_id})", version="0.1.0")
    handler = create_handler(agent, always_fail=always_fail)
    local_agent_name = _agent_name(agent.agent_id)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/.well-known/acp/agents/{agent_name}")
    def well_known(agent_name: str) -> dict[str, Any]:
        if agent_name != local_agent_name:
            raise HTTPException(status_code=404, detail="Unknown agent name")
        return agent.identity_document

    @app.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return agent.capabilities.to_dict()

    @app.post("/acp/inbox")
    def inbox(message: dict[str, Any]) -> dict[str, Any]:
        result = agent.handle_incoming(message, handler=handler)
        return result

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a demo ACP agent server")
    parser.add_argument("--agent-id", required=True, help="agent:<name>@<domain>")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--public-host", default="localhost")
    parser.add_argument("--relay-url", default="http://localhost:8080")
    parser.add_argument("--storage-dir", default=".acp-data")
    parser.add_argument("--trust-profile", default="domain_verified")
    parser.add_argument("--always-fail", action="store_true")
    args = parser.parse_args()

    endpoint = f"http://{args.public_host}:{args.port}/acp/inbox"
    agent = Agent.load_or_create(
        args.agent_id,
        storage_dir=args.storage_dir,
        endpoint=endpoint,
        relay_url=args.relay_url,
        relay_hints=[args.relay_url],
        discovery_scheme="http",
        trust_profile=args.trust_profile,
    )

    print(
        json.dumps(
            {
                "agent_id": agent.agent_id,
                "identity_document_endpoint": f"http://{args.public_host}:{args.port}/.well-known/acp/agents/{_agent_name(agent.agent_id)}",
                "inbox_endpoint": endpoint,
                "relay_url": args.relay_url,
            },
            indent=2,
        ),
    )

    app = build_app(agent, always_fail=args.always_fail)
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
