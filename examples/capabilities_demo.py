from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "acp-sdk-python"))

from acp import Agent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ACP CAPABILITIES exchange demo")
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

    result, capabilities = sender.request_capabilities(args.recipient_id)
    print("CAPABILITIES request result:")
    print(json.dumps(result.to_dict(), indent=2))
    print("Resolved capabilities:")
    print(json.dumps(capabilities, indent=2))


if __name__ == "__main__":
    main()
