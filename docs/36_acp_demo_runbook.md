
# ACP John Demo Runbook

## Goal
Demonstrate that ACP reduces adoption friction while preserving security, identity, and flexibility.

The demo shows three stages:

1. Direct agent-to-agent communication (no relay)
2. Relay-assisted communication with discovery and registration
3. Agent migration to cloud without client-side reconfiguration

Total demo time: ~5 minutes.

---

## Stage 1 — Direct HTTP Communication

### Setup
John runs locally:

python chess_agent.py --agent-id agent:john.chess@demo

You run locally:

python chess_agent.py --agent-id agent:ricardo.chess@demo

Agents communicate directly via HTTP.

### Message
“This is equivalent to today's VPN + webhook style integrations, but using ACP semantics.”

### Expected outcome
Agents exchange moves and ACK responses.

---

## Stage 2 — Relay + Registration + Discovery

Start relay (AWS):

acp relay run --config relay.yaml

Register your agent:

acp register put --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net

John discovers the agent:

acp discover get --agent-id agent:ricardo.chess@demo

Run the chess agents again.

### Message
“Now we remove the need for direct network reachability. Only configuration changes.”

### Expected outcome
Relay forwards encrypted messages.

---

## Stage 3 — Agent Migration

Move your chess agent to AWS.

Update registration:

acp register update --agent-id agent:ricardo.chess@demo --endpoint https://aws-chess.acp-demo.net/acp

John runs the same agent again without configuration changes.

### Message
“The agent identity stayed constant even though the infrastructure moved.”

### Expected outcome
Game continues normally.
