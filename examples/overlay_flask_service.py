from __future__ import annotations

import argparse
import json
from urllib.parse import urlparse

try:
    from flask import Flask, jsonify, request
except ImportError as exc:  # pragma: no cover - example runtime dependency
    raise SystemExit("Flask is required for this example: pip install flask") from exc

from acp.agent import Agent
from acp.overlay_framework import OverlayFrameworkRuntime, register_flask_overlay_routes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an ACP overlay-enabled Flask service around existing endpoints.",
    )
    parser.add_argument("--agent-id", default="agent:overlay.flask@localhost:9020")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9020)
    parser.add_argument("--base-url", default="http://localhost:9020")
    parser.add_argument("--storage-dir", default=".acp-data-overlay-flask")
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--allow-insecure-tls", action="store_true")
    parser.add_argument("--ca-file")
    parser.add_argument("--relay-url", default="http://localhost:8080")
    return parser.parse_args()


def _discovery_scheme(base_url: str) -> str:
    scheme = urlparse(base_url).scheme.lower()
    return "https" if scheme == "https" else "http"


def _build_app(args: argparse.Namespace) -> Flask:
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

    runtime = OverlayFrameworkRuntime.create(
        agent=agent,
        base_url=args.base_url,
        business_handler=lambda payload: {
            "accepted": True,
            "kind": payload.get("kind"),
            "echo": payload,
        },
        passthrough_handler=lambda body: {
            "accepted": True,
            "kind": body.get("kind"),
            "echo": body,
        },
    )

    app = Flask(__name__)
    register_flask_overlay_routes(app, runtime=runtime)

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.post("/orders")
    def orders() -> tuple[object, int]:
        body = request.get_json(silent=True)
        response = runtime.handle_message_body(body)
        return jsonify(response.body), response.status_code

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
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
