
# ACP John Demo Command Checklist

Security posture:

- these demo commands are local/demo focused
- production-style HTTP paths should use HTTPS endpoints by default

## John Machine

Create identity:

acp --allow-insecure-http identity create --agent-id agent:john.chess@demo

Discover opponent:

acp --allow-insecure-http discover get --agent-id agent:ricardo.chess@demo

Run chess agent:

acp --allow-insecure-http agent run --agent-id agent:john.chess@demo

---

## Ricardo Machine

Create identity:

acp --allow-insecure-http identity create --agent-id agent:ricardo.chess@demo

Register with relay:

acp register put --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net

Run chess agent:

acp --allow-insecure-http agent run --agent-id agent:ricardo.chess@demo

---

## Relay Commands

Show registry:

acp --allow-insecure-http relay registry list --relay http://localhost:8080

Inspect routes:

acp --allow-insecure-http relay routes show --relay http://localhost:8080

Show relay stats:

acp --allow-insecure-http relay ops stats --relay http://localhost:8080
