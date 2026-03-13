
# ACP Discovery Specification (Short Design Document)

## Overview

ACP discovery provides a decentralized mechanism for locating agents and determining how to communicate with them.

The discovery process maps:

agent identifier → identity document → reachability hints

---

## Agent Identifier Format

Agents are identified using:

agent:<name>@<domain>

Examples:

agent:inventory.bot@companyA.com
agent:research.agent@labX.org

---

## Discovery Mechanisms

ACP discovery may occur using the following mechanisms:

1. Local cache lookup
2. Domain-based discovery
3. Relay-assisted lookup
4. Enterprise directory lookup

Implementations should attempt discovery in that order.

---

## Domain Discovery

Agents hosted under a domain should expose identity documents via:

https://<domain>/.well-known/acp/agents/<agent_name>

Example:

https://companyB.com/.well-known/acp/agents/shipping.bot

DNS records may provide bootstrap hints.

---

## Discovery Document Structure

Example response:

{
  "agent_id": "agent:shipping.bot@companyB.com",
  "identity_document_url": "https://companyB.com/.well-known/acp/agents/shipping.bot",
  "service": {
    "direct_endpoint": "https://agents.companyB.com/acp",
    "relay_hints": [
      "relay.companyB.com",
      "relay.acp.network"
    ]
  },
  "trust_profile": "domain_verified",
  "valid_until": "2027-03-13T00:00:00Z"
}

---

## Relay-Assisted Discovery

Relays may provide:

- cached identity documents
- relay routing hints
- network reachability assistance

Relay data must be validated against the identity document.

---

## Enterprise Discovery

Enterprise deployments may provide private directories that return identity documents and routing policies.

These directories may include:

- trusted partner registries
- internal agent directories
- regulated industry identity systems

---

## SDK Discovery Behavior

Example SDK usage:

```python
agent.send(
    recipients=["agent:shipping.bot@companyB.com"],
    payload={"task": "ship_order"}
)
```

Internal SDK flow:

1. Resolve identity via cache
2. If missing or expired, perform domain discovery
3. Validate identity document
4. Select transport path
5. Deliver encrypted message

---

## Security Requirements

Discovery systems must ensure:

- identity document signatures are valid
- keys match identity document
- trust profiles are respected
- endpoints are protected by TLS

---

## Goal

ACP discovery enables agents to locate one another without requiring a centralized registry while allowing optional relay and enterprise infrastructure layers.
