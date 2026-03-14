
# ACP John Demo Fallback Plan

## If direct communication fails

Use relay mode immediately:

acp register put --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net

---

## If relay discovery fails

Manually configure endpoint:

acp message send --from agent:john.chess@demo --to agent:ricardo.chess@demo --transport http

---

## If cloud migration step fails

Keep relay-based configuration and restart local agent.

---

## Backup plan

Switch to poker demo to demonstrate:

- many-to-many communication
- relay routing
- identity verification
