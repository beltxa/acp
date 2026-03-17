from __future__ import annotations

import argparse
import json
from pathlib import Path
import ssl
import sys
from typing import Any

from fastapi import FastAPI
import uvicorn

try:
    from acp import Agent, FailReason, ProcessingError
    from acp.messages import Envelope
except ImportError:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "sdks" / "python"))
    from acp import Agent, FailReason, ProcessingError  # noqa: E402
    from acp.messages import Envelope  # noqa: E402


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


def build_app(agent: Agent, always_fail: bool, base_url: str) -> FastAPI:
    app = FastAPI(title=f"ACP Agent Node ({agent.agent_id})", version="0.1.0")
    handler = create_handler(agent, always_fail=always_fail)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/.well-known/acp")
    def well_known() -> dict[str, Any]:
        return agent.build_well_known_document(base_url=base_url)

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
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow local/dev/demo http:// endpoints",
    )
    parser.add_argument(
        "--allow-insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for HTTPS lookups",
    )
    parser.add_argument("--mtls-enabled", action="store_true", help="Enable optional HTTP mTLS profile")
    parser.add_argument("--ca-file", help="Custom CA bundle path")
    parser.add_argument("--cert-file", help="Server/client certificate path")
    parser.add_argument("--key-file", help="Server/client private key path")
    parser.add_argument("--trust-profile", default="domain_verified")
    parser.add_argument("--always-fail", action="store_true")
    args = parser.parse_args()

    endpoint_scheme = "https" if args.cert_file and args.key_file else "http"
    endpoint = f"{endpoint_scheme}://{args.public_host}:{args.port}/acp/inbox"
    agent = Agent.load_or_create(
        args.agent_id,
        storage_dir=args.storage_dir,
        endpoint=endpoint,
        relay_url=args.relay_url,
        relay_hints=[args.relay_url],
        discovery_scheme="http",
        trust_profile=args.trust_profile,
        allow_insecure_http=args.allow_insecure_http,
        allow_insecure_tls=args.allow_insecure_tls,
        mtls_enabled=args.mtls_enabled,
        ca_file=args.ca_file,
        cert_file=args.cert_file,
        key_file=args.key_file,
    )

    base_url = f"{endpoint_scheme}://{args.public_host}:{args.port}"
    print(
        json.dumps(
            {
                "agent_id": agent.agent_id,
                "well_known_endpoint": f"{base_url}/.well-known/acp",
                "identity_document_endpoint": f"{base_url}/api/v1/acp/identity",
                "inbox_endpoint": endpoint,
                "relay_url": args.relay_url,
            },
            indent=2,
        ),
    )

    app = build_app(agent, always_fail=args.always_fail, base_url=base_url)
    run_kwargs: dict[str, Any] = {"host": args.host, "port": args.port, "reload": False}
    if args.cert_file and args.key_file:
        run_kwargs["ssl_certfile"] = args.cert_file
        run_kwargs["ssl_keyfile"] = args.key_file
        if args.ca_file:
            run_kwargs["ssl_ca_certs"] = args.ca_file
        if args.mtls_enabled:
            run_kwargs["ssl_cert_reqs"] = int(ssl.CERT_REQUIRED)
    uvicorn.run(app, **run_kwargs)


if __name__ == "__main__":
    main()
