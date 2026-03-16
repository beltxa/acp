from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.parse import urlparse

from acp.agent import Agent
from acp.overlay_framework import OverlayClient


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a business payload through ACP overlay outbound helper.",
    )
    parser.add_argument("--from-agent-id", default="agent:overlay.sender@localhost:9011")
    parser.add_argument("--storage-dir", default=".acp-data-overlay-sender")
    parser.add_argument("--sender-endpoint", default="http://localhost:9011/outbox")
    parser.add_argument("--target-base-url", required=True)
    parser.add_argument("--to-agent-id")
    parser.add_argument("--payload-json", default='{"kind":"order.create","order_id":"demo-1"}')
    parser.add_argument("--context", default="overlay:example")
    parser.add_argument("--delivery-mode", choices=["auto", "direct", "relay"], default="auto")
    parser.add_argument("--expires-in-seconds", type=int, default=300)
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--allow-insecure-tls", action="store_true")
    parser.add_argument("--ca-file")
    parser.add_argument("--relay-url", default="http://localhost:8080")
    return parser.parse_args()


def _discovery_scheme(url: str) -> str:
    scheme = urlparse(url).scheme.lower()
    return "https" if scheme == "https" else "http"


def main() -> None:
    args = _parse_args()
    payload = json.loads(args.payload_json)
    if not isinstance(payload, dict):
        raise SystemExit("--payload-json must be a JSON object")

    sender = Agent.load_or_create(
        args.from_agent_id,
        storage_dir=args.storage_dir,
        endpoint=args.sender_endpoint,
        relay_url=args.relay_url,
        discovery_scheme=_discovery_scheme(args.target_base_url),
        allow_insecure_http=args.allow_insecure_http,
        allow_insecure_tls=args.allow_insecure_tls,
        ca_file=args.ca_file,
    )

    outbound = OverlayClient.create(agent=sender)
    result = outbound.send_acp(
        args.target_base_url,
        payload,
        recipient_agent_id=args.to_agent_id,
        context=args.context,
        delivery_mode=args.delivery_mode,
        expires_in_seconds=args.expires_in_seconds,
    )

    print(
        json.dumps(
            result,
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
