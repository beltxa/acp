
# ACP John Demo Command Checklist

## John Machine

Create identity:

acp identity create --agent-id agent:john.chess@demo

Discover opponent:

acp discover get --agent-id agent:ricardo.chess@demo

Run chess agent:

acp agent run --agent-id agent:john.chess@demo

---

## Ricardo Machine

Create identity:

acp identity create --agent-id agent:ricardo.chess@demo

Register with relay:

acp register put --agent-id agent:ricardo.chess@demo --relay https://relay.acp-demo.net

Run chess agent:

acp agent run --agent-id agent:ricardo.chess@demo

---

## Relay Commands

Show registry:

acp relay registry list

Inspect routes:

acp relay routes show --agent-id agent:ricardo.chess@demo

Show relay stats:

acp relay ops stats
