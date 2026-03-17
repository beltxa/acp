from __future__ import annotations

import logging
import os
import ssl
from threading import Event, Thread
import time

from fastapi import FastAPI, Request
import uvicorn

from http_security import RelayHttpSecurityPolicy, validate_http_security_policy
from key_provider import KeyProviderError, resolve_key_provider
from routing import RelayDiscoveryResolver, RelayRouter, RelayRoutingConfig
from routes import register_routes
from storage import MessageStore


LOGGER = logging.getLogger("acp.relay")


_SUPPORTED_ACP_ENV_VARS: set[str] = {
    "ACP_AMQP_BROKER_URL",
    "ACP_AMQP_EXCHANGE",
    "ACP_AMQP_EXCHANGE_TYPE",
    "ACP_ALLOW_INSECURE_HTTP",
    "ACP_ALLOW_INSECURE_TLS",
    "ACP_CA_FILE",
    "ACP_CERT_FILE",
    "ACP_DISCOVERY_SCHEME",
    "ACP_KEY_FILE",
    "ACP_KEY_PROVIDER",
    "ACP_LOG_LEVEL",
    "ACP_MTLS_ENABLED",
    "ACP_RELAY_DISCOVERY_HINTS",
    "ACP_RELAY_HOST",
    "ACP_RELAY_MAX_RETRY_ATTEMPTS",
    "ACP_RELAY_PORT",
    "ACP_RELAY_RETRY_BACKOFF_SECONDS",
    "ACP_RELAY_RETRY_INTERVAL_SECONDS",
    "ACP_RELAY_STORE_AND_FORWARD",
    "ACP_RELAY_TIMEOUT_SECONDS",
    "ACP_VAULT_PATH",
    "ACP_VAULT_TOKEN",
    "ACP_VAULT_TOKEN_ENV",
    "ACP_VAULT_URL",
}


def _configure_logging() -> None:
    raw_level = os.getenv("ACP_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, raw_level, logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    LOGGER.setLevel(level)


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


def _non_empty(raw: str | None) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    return normalized or None


def _validate_relay_dev_boundary() -> None:
    unsupported: list[str] = []
    for env_var, value in os.environ.items():
        if not env_var.startswith("ACP_"):
            continue
        if env_var in _SUPPORTED_ACP_ENV_VARS:
            continue
        normalized = value.strip()
        if not normalized:
            continue
        if normalized.lower() in {"0", "false", "no", "off"}:
            continue
        unsupported.append(env_var)
    if not unsupported:
        return
    env_labels = sorted(set(unsupported))
    raise RuntimeError(
        "Configuration not supported in relay-dev. "
        "Remove unsupported ACP_* settings: "
        + ", ".join(env_labels),
    )


def _load_security_config_from_env() -> dict[str, object]:
    relay_timeout = int(os.getenv("ACP_RELAY_TIMEOUT_SECONDS", "10"))
    allow_insecure_http = _as_bool(
        os.getenv("ACP_ALLOW_INSECURE_HTTP", "false"),
        default=False,
    )
    allow_insecure_tls = _as_bool(
        os.getenv("ACP_ALLOW_INSECURE_TLS", "false"),
        default=False,
    )
    mtls_enabled = _as_bool(
        os.getenv("ACP_MTLS_ENABLED", "false"),
        default=False,
    )
    ca_file = _non_empty(os.getenv("ACP_CA_FILE"))
    cert_file = _non_empty(os.getenv("ACP_CERT_FILE"))
    key_file = _non_empty(os.getenv("ACP_KEY_FILE"))
    key_provider_name = _non_empty(os.getenv("ACP_KEY_PROVIDER")) or "local"
    vault_url = _non_empty(os.getenv("ACP_VAULT_URL"))
    vault_path = _non_empty(os.getenv("ACP_VAULT_PATH"))
    vault_token_env = _non_empty(os.getenv("ACP_VAULT_TOKEN_ENV")) or "VAULT_TOKEN"
    vault_token = _non_empty(os.getenv("ACP_VAULT_TOKEN"))
    try:
        key_provider = resolve_key_provider(
            key_provider=key_provider_name,
            vault_url=vault_url,
            vault_path=vault_path,
            vault_token_env=vault_token_env,
            vault_token=vault_token,
            timeout_seconds=relay_timeout,
            ca_file=ca_file,
            allow_insecure_tls=allow_insecure_tls,
            allow_insecure_http=allow_insecure_http,
            cert_file=cert_file,
            key_file=key_file,
        )
    except KeyProviderError as exc:
        raise RuntimeError(f"Invalid relay key provider configuration: {exc}") from exc

    provider_tls = key_provider.load_tls_material("relay")
    provider_ca = key_provider.load_ca_bundle("relay")
    effective_ca_file = ca_file or provider_tls.ca_file or provider_ca
    effective_cert_file = cert_file or provider_tls.cert_file
    effective_key_file = key_file or provider_tls.key_file

    return {
        "relay_timeout": relay_timeout,
        "allow_insecure_http": allow_insecure_http,
        "allow_insecure_tls": allow_insecure_tls,
        "mtls_enabled": mtls_enabled,
        "ca_file": effective_ca_file,
        "cert_file": effective_cert_file,
        "key_file": effective_key_file,
        "key_provider_info": key_provider.describe(),
    }


def create_app() -> FastAPI:
    _configure_logging()
    _validate_relay_dev_boundary()
    discovery_scheme = os.getenv("ACP_DISCOVERY_SCHEME", "https")
    security_config = _load_security_config_from_env()
    relay_timeout = int(security_config["relay_timeout"])
    allow_insecure_http = bool(security_config["allow_insecure_http"])
    allow_insecure_tls = bool(security_config["allow_insecure_tls"])
    mtls_enabled = bool(security_config["mtls_enabled"])
    ca_file = security_config["ca_file"] if isinstance(security_config["ca_file"], str) else None
    cert_file = security_config["cert_file"] if isinstance(security_config["cert_file"], str) else None
    key_file = security_config["key_file"] if isinstance(security_config["key_file"], str) else None
    key_provider_info = (
        dict(security_config["key_provider_info"])
        if isinstance(security_config.get("key_provider_info"), dict)
        else {"provider": "unknown"}
    )
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
    policy = RelayHttpSecurityPolicy(
        allow_insecure_http=allow_insecure_http,
        allow_insecure_tls=allow_insecure_tls,
        ca_file=ca_file,
        mtls_enabled=mtls_enabled,
        cert_file=cert_file,
        key_file=key_file,
    )
    validate_http_security_policy(policy, context="Relay environment configuration")

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
        ca_file=ca_file,
        mtls_enabled=mtls_enabled,
        cert_file=cert_file,
        key_file=key_file,
        key_provider_info=key_provider_info,
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
        ca_file=ca_file,
        mtls_enabled=mtls_enabled,
        cert_file=cert_file,
        key_file=key_file,
        key_provider_info=key_provider_info,
    )

    app = FastAPI(title="ACP Reference Relay", version="0.1.0")
    register_routes(app, router=router, resolver=resolver, store=store)

    @app.middleware("http")
    async def _request_logging_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000.0
            LOGGER.exception(
                "request_failed method=%s path=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000.0
        LOGGER.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

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
    host = os.getenv("ACP_RELAY_HOST", "0.0.0.0")
    port = int(os.getenv("ACP_RELAY_PORT", "8080"))
    security_config = _load_security_config_from_env()
    mtls_enabled = bool(security_config["mtls_enabled"])
    cert_file = security_config["cert_file"] if isinstance(security_config["cert_file"], str) else None
    key_file = security_config["key_file"] if isinstance(security_config["key_file"], str) else None
    ca_file = security_config["ca_file"] if isinstance(security_config["ca_file"], str) else None

    run_kwargs: dict[str, object] = {
        "host": host,
        "port": port,
        "reload": False,
    }
    if cert_file and key_file:
        run_kwargs["ssl_certfile"] = cert_file
        run_kwargs["ssl_keyfile"] = key_file
        if ca_file:
            run_kwargs["ssl_ca_certs"] = ca_file
        if mtls_enabled:
            run_kwargs["ssl_cert_reqs"] = int(ssl.CERT_REQUIRED)

    uvicorn.run("app:app", **run_kwargs)
