from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "acp-sdk-python"))

from acp import Agent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ACP one-to-one SEND demo")
    parser.add_argument(
        "--sender-id",
        default="agent:inventory.bot@localhost:9000",
        help="Sender agent id",
    )
    parser.add_argument(
        "--recipient-id",
        default="agent:shipping.bot@localhost:9001",
        help="Recipient agent id",
    )
    parser.add_argument("--relay-url", default="http://localhost:8080")
    parser.add_argument("--storage-dir", default=".acp-data")
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow local/dev/demo http:// endpoints",
    )
    parser.add_argument("--context", default="order-12345")
    parser.add_argument(
        "--delivery-mode",
        choices=["auto", "direct", "relay"],
        default="auto",
        help="How the SDK should route outbound delivery",
    )
    args = parser.parse_args()

    sender_endpoint = "http://localhost:9000/acp/inbox"
    sender = Agent.load_or_create(
        args.sender_id,
        storage_dir=args.storage_dir,
        endpoint=sender_endpoint,
        relay_url=args.relay_url,
        relay_hints=[args.relay_url],
        discovery_scheme="http",
        trust_profile="domain_verified",
        allow_insecure_http=args.allow_insecure_http,
    )

    payload = {
        "type": "task_request",
        "data": {
            "task": "ship_order",
            "order_id": "12345",
        },
    }
    result = sender.send(
        recipients=[args.recipient_id],
        payload=payload,
        context=args.context,
        delivery_mode=args.delivery_mode,
    )
    print(json.dumps(result.to_dict(), indent=2))

    for outcome in result.outcomes:
        if outcome.response_message is None:
            continue
        try:
            response_message, response_payload = sender.decrypt_message_for_self(
                outcome.response_message,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Unable to decrypt response from {outcome.recipient}: {exc}")
            continue
        print(
            json.dumps(
                {
                    "recipient": outcome.recipient,
                    "response_class": response_message.envelope.message_class.value,
                    "response_payload": response_payload,
                },
                indent=2,
            ),
        )


if __name__ == "__main__":
    main()
