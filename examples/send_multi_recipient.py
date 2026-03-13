from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "acp-sdk-python"))

from acp import Agent, DeliveryState  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ACP one-to-many SEND demo")
    parser.add_argument(
        "--sender-id",
        default="agent:orchestrator.bot@localhost:9000",
        help="Sender agent id",
    )
    parser.add_argument(
        "--recipient",
        action="append",
        default=[
            "agent:shipping.bot@localhost:9001",
            "agent:finance.bot@localhost:9002",
        ],
        help="Recipient agent ids (repeatable)",
    )
    parser.add_argument(
        "--force-fail-recipient",
        default="agent:finance.bot@localhost:9002",
        help="Recipient id that should return FAIL in this demo",
    )
    parser.add_argument("--relay-url", default="http://localhost:8080")
    parser.add_argument("--storage-dir", default=".acp-data")
    parser.add_argument("--context", default="order-45678")
    parser.add_argument(
        "--delivery-mode",
        choices=["auto", "direct", "relay"],
        default="auto",
        help="How the SDK should route outbound delivery",
    )
    args = parser.parse_args()

    sender = Agent.load_or_create(
        args.sender_id,
        storage_dir=args.storage_dir,
        endpoint="http://localhost:9000/acp/inbox",
        relay_url=args.relay_url,
        relay_hints=[args.relay_url],
        discovery_scheme="http",
        trust_profile="domain_verified",
    )

    payload = {
        "type": "multi_task_request",
        "data": {
            "task": "reserve_and_invoice",
            "order_id": "45678",
        },
        "force_fail_for": [args.force_fail_recipient],
    }

    send_result = sender.send(
        recipients=args.recipient,
        payload=payload,
        context=args.context,
        delivery_mode=args.delivery_mode,
    )
    print("SEND result:")
    print(json.dumps(send_result.to_dict(), indent=2))

    successful_recipients: list[str] = []
    failed_recipients: list[str] = []
    for outcome in send_result.outcomes:
        if outcome.state in {DeliveryState.DELIVERED, DeliveryState.ACKNOWLEDGED}:
            successful_recipients.append(outcome.recipient)
        elif outcome.state is DeliveryState.FAILED:
            failed_recipients.append(outcome.recipient)

    if successful_recipients and failed_recipients:
        compensate_result = sender.send_compensate(
            recipients=successful_recipients,
            original_operation_id=send_result.operation_id,
            reason=(
                "Partial failure in one-to-many SEND operation: "
                + ",".join(failed_recipients)
            ),
            actions=[
                {"type": "cancel_reservation", "order_id": "45678"},
            ],
            context=f"compensate-{args.context}",
            delivery_mode=args.delivery_mode,
        )
        print("COMPENSATE result:")
        print(json.dumps(compensate_result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
