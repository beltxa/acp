from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
import uvicorn

from acp.agent import Agent
from acp.overlay import OverlayInboundAdapter


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an ACP overlay-enabled HTTP service on top of an existing business endpoint.",
    )
    parser.add_argument("--agent-id", default="agent:overlay.receiver@localhost:9010")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9010)
    parser.add_argument("--base-url", default="http://localhost:9010")
    parser.add_argument("--storage-dir", default=".acp-data-overlay-receiver")
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--allow-insecure-tls", action="store_true")
    parser.add_argument("--ca-file")
    parser.add_argument("--relay-url", default="http://localhost:8080")
    return parser.parse_args()


def _discovery_scheme(base_url: str) -> str:
    scheme = urlparse(base_url).scheme.lower()
    return "https" if scheme == "https" else "http"


def _build_app(args: argparse.Namespace) -> FastAPI:
    endpoint = f"{args.base_url.rstrip('/')}/orders"
    agent = Agent.load_or_create(
        args.agent_id,
        storage_dir=args.storage_dir,
        endpoint=endpoint,
        relay_url=args.relay_url,
        discovery_scheme=_discovery_scheme(args.base_url),
        allow_insecure_http=args.allow_insecure_http,
        allow_insecure_tls=args.allow_insecure_tls,
        ca_file=args.ca_file,
    )

    def business_handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "accepted": True,
            "kind": payload.get("kind"),
            "echo": payload,
        }

    adapter = OverlayInboundAdapter(
        agent=agent,
        business_handler=business_handler,
        passthrough_handler=lambda body: business_handler(body),
    )

    app = FastAPI(title="ACP Overlay Example Service", version="1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/acp/identity")
    def identity_document() -> dict[str, Any]:
        return {"identity_document": agent.identity_document}

    @app.get("/.well-known/acp")
    def well_known() -> dict[str, Any]:
        return agent.build_well_known_document(base_url=args.base_url)

    @app.post("/orders")
    async def orders(request: Request) -> dict[str, Any]:
        body = await request.json()
        if not isinstance(body, dict):
            return {"mode": "invalid", "detail": "Expected JSON object body"}
        return adapter.handle_request(body)

    return app


def main() -> None:
    args = _parse_args()
    app = _build_app(args)
    print(
        json.dumps(
            {
                "agent_id": args.agent_id,
                "base_url": args.base_url,
                "orders_endpoint": f"{args.base_url.rstrip('/')}/orders",
                "well_known_endpoint": f"{args.base_url.rstrip('/')}/.well-known/acp",
            },
            indent=2,
        ),
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
