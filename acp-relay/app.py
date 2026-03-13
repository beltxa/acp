from __future__ import annotations

import os

from fastapi import FastAPI
import uvicorn

from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig
from routes import register_routes
from storage import MessageStore


def _relay_hints_from_env() -> list[str]:
    raw = os.getenv("ACP_RELAY_DISCOVERY_HINTS", "")
    if not raw.strip():
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app() -> FastAPI:
    discovery_scheme = os.getenv("ACP_DISCOVERY_SCHEME", "https")
    relay_timeout = int(os.getenv("ACP_RELAY_TIMEOUT_SECONDS", "10"))
    routing_config = RelayRoutingConfig(
        default_scheme=discovery_scheme,
        timeout_seconds=relay_timeout,
        relay_hints=_relay_hints_from_env(),
    )
    resolver = RelayDiscoveryResolver(routing_config)
    router = RelayRouter(resolver, timeout_seconds=relay_timeout)
    store = MessageStore()

    app = FastAPI(title="ACP Reference Relay", version="0.1.0")
    register_routes(app, router=router, resolver=resolver, store=store)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("ACP_RELAY_HOST", "0.0.0.0"),
        port=int(os.getenv("ACP_RELAY_PORT", "8080")),
        reload=False,
    )
