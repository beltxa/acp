from __future__ import annotations

import json
from pathlib import Path
import sys

try:
    from acp import Agent, AgentCapabilities
except ImportError:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "sdks" / "python"))
    from acp import Agent, AgentCapabilities  # noqa: E402

agent_id = "agent:hello.world@localhost:9012"
capabilities = AgentCapabilities(agent_id=agent_id)
capabilities.supports["ping"] = True
agent = Agent.load_or_create(
    agent_id,
    storage_dir=".acp-data",
    endpoint="http://localhost:9012/acp/inbox",
    relay_url="http://localhost:8080",
    relay_hints=["http://localhost:8080"],
    discovery_scheme="http",
    allow_insecure_http=True,
    capabilities=capabilities,
)
print(
    json.dumps(
        {
            "agent_id": agent.agent_id,
            "capability_ping": agent.capabilities.supports.get("ping", False),
        },
        indent=2,
    )
)
