from __future__ import annotations

import os
from threading import Event, Thread

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


def _as_bool(raw: str, *, default: bool) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def create_app() -> FastAPI:
    discovery_scheme = os.getenv("ACP_DISCOVERY_SCHEME", "https")
    relay_timeout = int(os.getenv("ACP_RELAY_TIMEOUT_SECONDS", "10"))
    allow_insecure_http = _as_bool(
        os.getenv("ACP_ALLOW_INSECURE_HTTP", "false"),
        default=False,
    )
    allow_insecure_tls = _as_bool(
        os.getenv("ACP_ALLOW_INSECURE_TLS", "false"),
        default=False,
    )
    ca_file = os.getenv("ACP_CA_FILE")
    amqp_broker_url = os.getenv("ACP_AMQP_BROKER_URL")
    amqp_exchange = os.getenv("ACP_AMQP_EXCHANGE", "acp.exchange")
    amqp_exchange_type = os.getenv("ACP_AMQP_EXCHANGE_TYPE", "direct")
    store_and_forward = _as_bool(
        os.getenv("ACP_RELAY_STORE_AND_FORWARD", "true"),
        default=True,
    )
    retry_interval_seconds = float(os.getenv("ACP_RELAY_RETRY_INTERVAL_SECONDS", "2"))
    max_retry_attempts = int(os.getenv("ACP_RELAY_MAX_RETRY_ATTEMPTS", "3"))
    retry_backoff_seconds = float(os.getenv("ACP_RELAY_RETRY_BACKOFF_SECONDS", "2"))
    routing_config = RelayRoutingConfig(
        default_scheme=discovery_scheme,
        timeout_seconds=relay_timeout,
        relay_hints=_relay_hints_from_env(),
        store_and_forward=store_and_forward,
        max_retry_attempts=max_retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        amqp_broker_url=amqp_broker_url,
        amqp_exchange=amqp_exchange,
        amqp_exchange_type=amqp_exchange_type,
        allow_insecure_http=allow_insecure_http,
        allow_insecure_tls=allow_insecure_tls,
        ca_file=ca_file.strip() if isinstance(ca_file, str) and ca_file.strip() else None,
    )
    resolver = RelayDiscoveryResolver(routing_config)
    store = MessageStore()
    router = RelayRouter(
        resolver,
        timeout_seconds=relay_timeout,
        store=store,
        store_and_forward=store_and_forward,
        max_retry_attempts=max_retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        amqp_broker_url=amqp_broker_url,
        amqp_exchange=amqp_exchange,
        amqp_exchange_type=amqp_exchange_type,
        allow_insecure_http=allow_insecure_http,
        allow_insecure_tls=allow_insecure_tls,
        ca_file=ca_file.strip() if isinstance(ca_file, str) and ca_file.strip() else None,
    )

    app = FastAPI(title="ACP Reference Relay", version="0.1.0")
    register_routes(app, router=router, resolver=resolver, store=store)

    stop_event = Event()
    app.state.retry_worker_stop_event = stop_event
    app.state.retry_worker_thread = None

    @app.on_event("startup")
    def _start_retry_worker() -> None:
        if not store_and_forward:
            return

        def _run() -> None:
            while not stop_event.wait(retry_interval_seconds):
                router.process_pending_deliveries()

        worker = Thread(target=_run, daemon=True, name="acp-relay-retry-worker")
        worker.start()
        app.state.retry_worker_thread = worker

    @app.on_event("shutdown")
    def _stop_retry_worker() -> None:
        stop_event.set()
        worker = app.state.retry_worker_thread
        if worker is not None:
            worker.join(timeout=max(1.0, retry_interval_seconds))

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("ACP_RELAY_HOST", "0.0.0.0"),
        port=int(os.getenv("ACP_RELAY_PORT", "8080")),
        reload=False,
    )
