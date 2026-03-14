# ACP CLI v1 (Phases 1-4)

This CLI is a thin operational wrapper over the existing ACP Python SDK.
It does not re-implement ACP protocol logic.

Current phase includes:

- `acp identity create`
- `acp identity show`
- `acp identity export`
- `acp identity verify`
- `acp discover get`
- `acp discover list`
- `acp register put`
- `acp register update`
- `acp register show`
- `acp message send`
- `acp message capabilities`
- `acp agent run`
- `acp agent status`
- `acp transport list`
- `acp transport probe`
- `acp relay status`
- `acp relay health`
- `acp relay registry list`
- `acp relay registry show`
- `acp relay routes show`
- `acp relay ops stats`
- `acp relay ops failures`

## Installation

From repository root:

```bash
pip install -e acp-sdk-python
```

Then run:

```bash
acp --help
```

## Config

CLI reads optional JSON config from:

- `--config <path>`
- or `ACP_CONFIG_FILE`
- or `~/.acp/config.json` if it exists

Supported config keys:

```json
{
  "storage_dir": ".acp-data",
  "discovery_scheme": "https",
  "relay_hints": ["http://localhost:8080"],
  "enterprise_directory_hints": [],
  "timeout_seconds": 5
}
```

You can override storage directly:

```bash
acp --storage-dir /tmp/acp-data identity show --agent-id agent:demo@localhost:8088
```

## Examples

Create identity:

```bash
acp identity create --agent-id agent:john.chess@demo
```

Create identity with endpoint and relay hint:

```bash
acp identity create \
  --agent-id agent:john.chess@demo \
  --direct-endpoint http://localhost:8088/api/v1/acp/messages \
  --relay-hint http://localhost:8080
```

Show identity:

```bash
acp identity show --agent-id agent:john.chess@demo
```

Export identity document:

```bash
acp identity export --agent-id agent:john.chess@demo --out ./john.identity.json
```

Verify identity document:

```bash
acp identity verify --file ./john.identity.json
```

Discover identity:

```bash
acp discover get --agent-id agent:ricardo.chess@demo
```

List discovery cache:

```bash
acp discover list
```

Register local identity with relay:

```bash
acp register put \
  --agent-id agent:john.chess@demo \
  --relay http://localhost:8080 \
  --endpoint http://localhost:8088/api/v1/acp/messages
```

Update registration to publish MQTT hint:

```bash
acp register update \
  --agent-id agent:john.chess@demo \
  --relay http://localhost:8080 \
  --transport mqtt \
  --broker mqtt://localhost:1883 \
  --topic acp/agent/john.chess.demo \
  --qos 1
```

Show relay registration:

```bash
acp register show --agent-id agent:john.chess@demo --relay http://localhost:8080
```

Send message payload:

```bash
acp message send \
  --from agent:john.chess@demo \
  --to agent:ricardo.chess@demo \
  --payload-json '{"kind":"ping","value":1}' \
  --delivery-mode auto
```

Request capabilities:

```bash
acp message capabilities \
  --from agent:john.chess@demo \
  --to agent:ricardo.chess@demo
```

Run a local agent runtime:

```bash
acp agent run \
  --agent-id agent:john.chess@localhost:8088 \
  --transport direct \
  --transport amqp \
  --port 8088
```

Check agent status:

```bash
acp agent status \
  --agent-id agent:john.chess@localhost:8088 \
  --relay http://localhost:8080
```

List transport configuration:

```bash
acp transport list --agent-id agent:john.chess@localhost:8088
```

Probe transport reachability:

```bash
acp transport probe --agent-id agent:john.chess@localhost:8088
```

Relay status:

```bash
acp relay status --relay http://localhost:8080
```

Relay health:

```bash
acp relay health --relay http://localhost:8080
```

Relay registry list/show:

```bash
acp relay registry list --relay http://localhost:8080 --limit 50
acp relay registry show --relay http://localhost:8080 --agent-id agent:john.chess@localhost:8088
```

Relay routes and ops:

```bash
acp relay routes show --relay http://localhost:8080 --limit 50
acp relay ops stats --relay http://localhost:8080
acp relay ops failures --relay http://localhost:8080 --limit 50
```

JSON output:

```bash
acp --json discover get --agent-id agent:ricardo.chess@demo
```

## Security Notes

- Private keys are never printed by default.
- Identity verification uses existing SDK identity verification logic.
- Discovery uses existing SDK discovery order (cache, `.well-known`, relay/directory hints).
- No insecure identity bypass is added in this phase.
- `acp message capabilities` reports non-error no-response outcomes explicitly.
