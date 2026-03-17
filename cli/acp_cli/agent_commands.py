# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
from threading import Event, Lock, Thread
import time
from typing import Any, Callable
from urllib.parse import urlparse

from acp.agent import Agent
from acp.identity import parse_agent_id, read_identity
from acp.relay_client import RelayClient
from acp.transport import TransportError

from .common import (
    CliContext,
    CliUserError,
    build_http_transport,
    build_key_provider,
    http_security_profile,
    identity_storage_dir,
    key_provider_metadata,
    runtime_status_path,
    service_security_profile,
    url_security_state,
)


DIRECT_INBOX_PATH = "/api/v1/acp/messages"


def register_agent_commands(domain_parser: argparse.ArgumentParser) -> None:
    subparsers = domain_parser.add_subparsers(dest="agent_command", required=True)

    run_cmd = subparsers.add_parser("run", help="Run local ACP agent listeners and transport loops")
    run_cmd.add_argument("--agent-id", required=True, help="ACP agent identifier")
    run_cmd.add_argument(
        "--transport",
        action="append",
        choices=["direct", "relay", "amqp", "mqtt", "http", "https"],
        help="Transport to activate (repeatable). Defaults to direct.",
    )
    run_cmd.add_argument("--port", type=int, help="Direct listener port override")
    run_cmd.add_argument("--relay", help="Relay URL override")
    run_cmd.add_argument("--out-dir", help="Identity storage directory override")
    run_cmd.set_defaults(handler=handle_agent_run)

    status_cmd = subparsers.add_parser("status", help="Show local ACP agent runtime/config status")
    status_cmd.add_argument("--agent-id", required=True, help="ACP agent identifier")
    status_cmd.add_argument("--relay", help="Relay URL for optional registration lookup")
    status_cmd.add_argument("--out-dir", help="Identity storage directory override")
    status_cmd.set_defaults(handler=handle_agent_status)


def handle_agent_run(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    storage_dir = identity_storage_dir(ctx, args.out_dir)
    requested = _normalize_transports(args.transport)
    effective, notes = _effective_transports(requested)

    tls_listener_enabled = bool(ctx.config.cert_file and ctx.config.key_file)
    endpoint = _resolve_endpoint(
        args.agent_id,
        args.port,
        use_https=tls_listener_enabled or ctx.config.mtls_enabled,
    )
    kwargs: dict[str, Any] = {
        "storage_dir": storage_dir,
        "discovery_scheme": ctx.config.discovery_scheme,
        "relay_hints": ctx.config.relay_hints,
        "enterprise_directory_hints": ctx.config.enterprise_directory_hints,
        "allow_insecure_http": ctx.config.allow_insecure_http,
        "allow_insecure_tls": ctx.config.allow_insecure_tls,
        "ca_file": ctx.config.ca_file,
        "mtls_enabled": ctx.config.mtls_enabled,
        "cert_file": ctx.config.cert_file,
        "key_file": ctx.config.key_file,
        "key_provider": build_key_provider(ctx, storage_dir=storage_dir),
    }
    if "direct" in effective:
        kwargs["endpoint"] = endpoint

    relay_url = args.relay.strip() if isinstance(args.relay, str) and args.relay.strip() else None
    if relay_url is not None:
        kwargs["relay_url"] = relay_url
        kwargs["relay_hints"] = [relay_url, *ctx.config.relay_hints]

    agent = Agent.load_or_create(args.agent_id, **kwargs)
    provider_info_raw = getattr(agent, "key_provider_info", None)
    provider_info = dict(provider_info_raw) if isinstance(provider_info_raw, dict) else {
        "provider": ctx.config.key_provider,
    }
    status_file = runtime_status_path(storage_dir, args.agent_id)
    runtime = AgentRuntime(
        agent=agent,
        agent_id=args.agent_id,
        transports=effective,
        endpoint=endpoint,
        direct_host="0.0.0.0",
        direct_port=urlparse(endpoint).port or 8080,
        status_file=status_file,
        relay_url=relay_url,
        poll_interval_seconds=max(0.2, min(5.0, ctx.config.timeout_seconds / 5.0)),
        tls_listener_enabled=tls_listener_enabled,
        mtls_enabled=ctx.config.mtls_enabled,
        ca_file=ctx.config.ca_file,
        cert_file=ctx.config.cert_file,
        key_file=ctx.config.key_file,
        key_provider=provider_info,
    )
    summary = runtime.run_forever()
    return {
        "_human": [
            "Agent runtime stopped",
            f"Agent ID: {args.agent_id}",
            f"Transports: {', '.join(effective)}",
            f"Endpoint: {endpoint if 'direct' in effective else '-'}",
            f"Endpoint security: {url_security_state(endpoint if 'direct' in effective else None)}",
            f"HTTP security profile: {http_security_profile(ctx)}",
            f"Key provider: {provider_info.get('provider', ctx.config.key_provider)}",
            *[f"Note: {note}" for note in notes],
        ],
        "ok": True,
        "agent_id": args.agent_id,
        "requested_transports": requested,
        "effective_transports": effective,
        "notes": notes,
        "endpoint": endpoint if "direct" in effective else None,
        "security": {
            "endpoint": url_security_state(endpoint if "direct" in effective else None),
            "relay": url_security_state(relay_url),
            "http_profile": http_security_profile(ctx),
        },
        "status_file": str(status_file),
        "runtime_summary": summary,
        "key_provider": provider_info,
    }


def handle_agent_status(args: argparse.Namespace, ctx: CliContext) -> dict[str, Any]:
    storage_dir = identity_storage_dir(ctx, args.out_dir)
    bundle = read_identity(storage_dir, args.agent_id)
    if bundle is None:
        raise CliUserError(
            message=f"Identity not found for {args.agent_id}",
            code="identity_not_found",
            details={"agent_id": args.agent_id, "storage_dir": str(storage_dir)},
            exit_code=2,
        )
    _, identity_document = bundle

    status_path = runtime_status_path(storage_dir, args.agent_id)
    runtime_state = _load_runtime_state(status_path)
    running = _runtime_running(runtime_state)
    service = identity_document.get("service", {})
    capabilities = identity_document.get("capabilities", {})

    relay_for_check = args.relay or (ctx.config.relay_hints[0] if ctx.config.relay_hints else None)
    registration_state: dict[str, Any] | None = None
    if relay_for_check:
        registration_state = _fetch_registration_state(args.agent_id, relay_for_check, ctx=ctx)
    provider_info = key_provider_metadata(ctx, storage_dir=storage_dir)

    return {
        "_human": [
            "Agent status",
            f"Agent ID: {args.agent_id}",
            f"Running: {'yes' if running else 'no'}",
            f"Runtime status file: {status_path}",
            f"Configured transports: {', '.join(capabilities.get('transports', [])) or '-'}",
            f"Direct endpoint: {service.get('direct_endpoint')}",
            f"Direct endpoint security: {url_security_state(service.get('direct_endpoint'))}",
            f"Relay hints: {', '.join(service.get('relay_hints', [])) or '-'}",
            f"HTTP security profile: {service_security_profile(service) or 'https'}",
            f"Key provider: {provider_info.get('provider', ctx.config.key_provider)}",
            (
                f"Registration ({relay_for_check}): "
                f"{'registered' if registration_state and registration_state.get('registered') else 'not registered'}"
            )
            if relay_for_check
            else "Registration: not checked",
        ],
        "ok": True,
        "agent_id": args.agent_id,
        "running": running,
        "runtime_state": runtime_state,
        "runtime_status_file": str(status_path),
        "configured": {
            "transports": capabilities.get("transports", []),
            "supports": capabilities.get("supports", {}),
            "service": {
                "direct_endpoint": service.get("direct_endpoint"),
                "relay_hints": service.get("relay_hints", []),
                "amqp": service.get("amqp"),
                "mqtt": service.get("mqtt"),
            },
            "security": {
                "direct_endpoint": url_security_state(service.get("direct_endpoint")),
                "relay_hints": [
                    {"url": str(item), "state": url_security_state(str(item))}
                    for item in service.get("relay_hints", [])
                    if isinstance(item, str)
                ],
                "http_profile": (
                    service.get("http", {}).get("security_profile")
                    if isinstance(service.get("http"), dict)
                    else None
                ),
                "relay_profile": (
                    service.get("relay", {}).get("security_profile")
                    if isinstance(service.get("relay"), dict)
                    else None
                ),
            },
        },
        "key_provider": provider_info,
        "registration": registration_state,
    }


class AgentRuntime:
    def __init__(
        self,
        *,
        agent: Agent,
        agent_id: str,
        transports: list[str],
        endpoint: str,
        direct_host: str,
        direct_port: int,
        status_file: Path,
        relay_url: str | None,
        poll_interval_seconds: float,
        tls_listener_enabled: bool,
        mtls_enabled: bool,
        ca_file: str | None,
        cert_file: str | None,
        key_file: str | None,
        key_provider: dict[str, Any] | None,
    ) -> None:
        self.agent = agent
        self.agent_id = agent_id
        self.transports = transports
        self.endpoint = endpoint
        self.direct_host = direct_host
        self.direct_port = direct_port
        self.status_file = status_file
        self.relay_url = relay_url
        self.poll_interval_seconds = poll_interval_seconds
        self.tls_listener_enabled = tls_listener_enabled
        self.mtls_enabled = mtls_enabled
        self.ca_file = ca_file
        self.cert_file = cert_file
        self.key_file = key_file
        self.key_provider = dict(key_provider or {})
        self._stop_event = Event()
        self._lock = Lock()
        self._direct_server: ThreadingHTTPServer | None = None
        self._threads: list[Thread] = []
        self._started_at = _now_iso()
        self._last_activity_at = self._started_at
        self._processed_inbound = 0
        self._transport_errors: list[dict[str, str]] = []

    def run_forever(self) -> dict[str, Any]:
        self._write_status("running")
        self._start_workers()
        try:
            while not self._stop_event.wait(0.5):
                self._write_status("running")
        except KeyboardInterrupt:
            pass
        finally:
            self._stop_event.set()
            self._stop_workers()
            self._write_status("stopped")

        with self._lock:
            return {
                "started_at": self._started_at,
                "last_activity_at": self._last_activity_at,
                "processed_inbound": self._processed_inbound,
                "transport_errors": list(self._transport_errors),
            }

    def _start_workers(self) -> None:
        if "direct" in self.transports:
            self._start_direct_server()
        if "amqp" in self.transports:
            self._start_thread("amqp-consumer", self._consume_amqp_loop)
        if "mqtt" in self.transports:
            self._start_thread("mqtt-consumer", self._consume_mqtt_loop)

    def _stop_workers(self) -> None:
        if self._direct_server is not None:
            try:
                self._direct_server.shutdown()
            except Exception:
                pass
            try:
                self._direct_server.server_close()
            except Exception:
                pass
            self._direct_server = None

        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=3.0)

    def _start_direct_server(self) -> None:
        runtime = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write_json(HTTPStatus.OK, {"status": "ok"})
                    return
                if self.path == "/api/v1/acp/identity":
                    self._write_json(HTTPStatus.OK, {"identity_document": runtime.agent.identity_document})
                    return
                if self.path == "/.well-known/acp":
                    endpoint_scheme = "https" if runtime.tls_listener_enabled else "http"
                    base_url = f"{endpoint_scheme}://{runtime.direct_host}:{runtime.direct_port}"
                    self._write_json(HTTPStatus.OK, runtime.agent.build_well_known_document(base_url=base_url))
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != DIRECT_INBOX_PATH:
                    self._write_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
                    return
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                try:
                    raw = self.rfile.read(content_length)
                    message = json.loads(raw.decode("utf-8"))
                    if not isinstance(message, dict):
                        raise ValueError("Request body must be a JSON object")
                except Exception as exc:
                    self._write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"detail": f"Invalid JSON payload: {exc}"},
                    )
                    return

                result = runtime.agent.handle_incoming(
                    message,
                    handler=runtime._inbound_handler,
                )
                runtime._mark_activity()
                self._write_json(HTTPStatus.OK, result)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _write_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
                payload = json.dumps(body, sort_keys=True).encode("utf-8")
                self.send_response(int(status))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer((self.direct_host, self.direct_port), Handler)
        if self.tls_listener_enabled:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            cert_file = self.cert_file or ""
            key_file = self.key_file or ""
            ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
            if self.ca_file:
                ssl_context.load_verify_locations(cafile=self.ca_file)
            if self.mtls_enabled:
                ssl_context.verify_mode = ssl.CERT_REQUIRED
            server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
        self._direct_server = server
        self._start_thread("direct-listener", server.serve_forever)

    def _start_thread(self, name: str, target: Callable[[], None]) -> None:
        thread = Thread(target=target, daemon=True, name=f"acp-cli-{name}")
        thread.start()
        self._threads.append(thread)

    def _consume_amqp_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.agent.consume_from_amqp(
                    handler=self._inbound_handler,
                    max_messages=10,
                )
                if processed > 0:
                    self._mark_activity(processed=processed)
            except Exception as exc:
                self._record_transport_error("amqp", str(exc))
            self._stop_event.wait(self.poll_interval_seconds)

    def _consume_mqtt_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.agent.consume_from_mqtt(
                    handler=self._inbound_handler,
                    max_messages=10,
                )
                if processed > 0:
                    self._mark_activity(processed=processed)
            except Exception as exc:
                self._record_transport_error("mqtt", str(exc))
            self._stop_event.wait(self.poll_interval_seconds)

    def _inbound_handler(self, payload: dict[str, Any], _envelope: Any) -> dict[str, Any]:
        self._mark_activity()
        return {
            "accepted": True,
            "payload_keys": sorted(payload.keys())[:10],
        }

    def _mark_activity(self, *, processed: int = 1) -> None:
        with self._lock:
            self._processed_inbound += max(1, processed)
            self._last_activity_at = _now_iso()

    def _record_transport_error(self, transport: str, detail: str) -> None:
        with self._lock:
            self._transport_errors.append(
                {
                    "transport": transport,
                    "detail": detail,
                    "at": _now_iso(),
                },
            )

    def _write_status(self, state: str) -> None:
        with self._lock:
            payload: dict[str, Any] = {
                "agent_id": self.agent_id,
                "pid": os.getpid(),
                "state": state,
                "started_at": self._started_at,
                "last_activity_at": self._last_activity_at,
                "transports": self.transports,
                "endpoint": self.endpoint if "direct" in self.transports else None,
                "relay": self.relay_url,
                "http_security_profile": (
                    "https+mtls"
                    if self.mtls_enabled
                    else "https"
                    if self.tls_listener_enabled
                    else "http"
                ),
                "mtls_enabled": self.mtls_enabled,
                "processed_inbound": self._processed_inbound,
                "transport_errors": self._transport_errors[-10:],
                "key_provider": self.key_provider,
                "updated_at": _now_iso(),
            }
            if state != "running":
                payload["stopped_at"] = _now_iso()

        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_transports(values: list[str] | None) -> list[str]:
    if not values:
        return ["direct"]
    normalized: list[str] = []
    for value in values:
        v = value.strip().lower()
        if v in {"http", "https"}:
            v = "direct"
        if v not in {"direct", "relay", "amqp", "mqtt"}:
            raise CliUserError(
                message=f"Unsupported transport: {value}",
                code="agent_invalid_args",
                exit_code=2,
            )
        if v not in normalized:
            normalized.append(v)
    return normalized


def _effective_transports(requested: list[str]) -> tuple[list[str], list[str]]:
    effective = list(requested)
    notes: list[str] = []
    if "relay" in requested and "direct" not in effective:
        effective.insert(0, "direct")
        notes.append("relay selected: direct listener enabled for inbound relay delivery")
    return effective, notes


def _resolve_endpoint(agent_id: str, port_override: int | None, *, use_https: bool) -> str:
    _, domain = parse_agent_id(agent_id)
    host = "localhost"
    port = port_override
    if domain:
        if ":" in domain:
            maybe_host, maybe_port = domain.rsplit(":", 1)
            if maybe_host:
                host = maybe_host
            if port is None:
                try:
                    port = int(maybe_port)
                except Exception:
                    port = None
        else:
            host = domain
    if port is None:
        port = 8080
    scheme = "https" if use_https else "http"
    return f"{scheme}://{host}:{port}{DIRECT_INBOX_PATH}"


def _load_runtime_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _runtime_running(runtime_state: dict[str, Any] | None) -> bool:
    if not runtime_state:
        return False
    if runtime_state.get("state") != "running":
        return False
    pid = runtime_state.get("pid")
    if not isinstance(pid, int):
        return False
    return _pid_is_running(pid)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _fetch_registration_state(agent_id: str, relay_url: str, *, ctx: CliContext) -> dict[str, Any]:
    client = RelayClient(relay_url, transport=build_http_transport(ctx))
    try:
        identity_document = client.discover_identity(agent_id)
        service = identity_document.get("service", {}) if isinstance(identity_document.get("service"), dict) else {}
        return {
            "checked": True,
            "registered": True,
            "relay": relay_url,
            "service": service,
            "security": {
                "relay": url_security_state(relay_url),
                "direct_endpoint": url_security_state(
                    service.get("direct_endpoint"),
                ),
                "http_profile": (
                    service.get("http", {}).get("security_profile")
                    if isinstance(service.get("http"), dict)
                    else None
                ),
                "relay_profile": (
                    service.get("relay", {}).get("security_profile")
                    if isinstance(service.get("relay"), dict)
                    else None
                ),
            },
        }
    except TransportError as exc:
        return {
            "checked": True,
            "registered": False,
            "relay": relay_url,
            "detail": str(exc),
            "security": {"relay": url_security_state(relay_url)},
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
