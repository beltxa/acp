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
- `acp discover well-known`
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
- `acp config show`
- `acp config validate`

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
  "relay_hints": ["https://relay.example"],
  "enterprise_directory_hints": [],
  "timeout_seconds": 5,
  "allow_insecure_http": false,
  "allow_insecure_tls": false,
  "ca_file": null,
  "mtls_enabled": false,
  "cert_file": null,
  "key_file": null,
  "key_provider": "local",
  "vault_url": null,
  "vault_path": null,
  "vault_token_env": "VAULT_TOKEN"
}
```

Global transport hardening flags:

- `--allow-insecure-http` local/dev/demo exception for `http://`
- `--allow-insecure-tls` disable TLS certificate verification
- `--ca-file <path>` custom CA bundle for HTTPS verification
- `--mtls-enabled` enable optional enterprise HTTP mTLS profile
- `--cert-file <path>` client/server certificate for mTLS profile
- `--key-file <path>` client/server private key for mTLS profile
- `--key-provider <local|vault>` select key custody backend
- `--vault-url <url>` Vault base URL when provider is `vault`
- `--vault-path <path>` Vault secret path prefix (or `{agent_id}` template)
- `--vault-token-env <name>` env var containing the Vault token

When `key_provider=vault` and `mtls_enabled=true`, `cert_file`/`key_file` may be supplied by provider material (leave both unset) or overridden explicitly (set both).

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
  --direct-endpoint https://john.example.net/api/v1/acp/messages \
  --relay-hint https://relay.example.net
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

Discover agent metadata from `/.well-known/acp`:

```bash
acp discover well-known https://ricardo.example.net --agent-id agent:ricardo.chess@demo
```

List discovery cache:

```bash
acp discover list
```

Register local identity with relay:

```bash
acp register put \
  --agent-id agent:john.chess@demo \
  --relay https://relay.example.net \
  --endpoint https://john.example.net/api/v1/acp/messages
```

Update registration to publish MQTT hint:

```bash
acp register update \
  --agent-id agent:john.chess@demo \
  --relay https://relay.example.net \
  --transport mqtt \
  --broker mqtt://localhost:1883 \
  --topic acp/agent/john.chess.demo \
  --qos 1
```

Show relay registration:

```bash
acp register show --agent-id agent:john.chess@demo --relay https://relay.example.net
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
  --relay https://relay.example.net
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
acp relay status --relay https://relay.example.net
```

Relay health:

```bash
acp relay health --relay https://relay.example.net
```

Relay registry list/show:

```bash
acp relay registry list --relay https://relay.example.net --limit 50
acp relay registry show --relay https://relay.example.net --agent-id agent:john.chess@localhost:8088
```

Relay routes and ops:

```bash
acp relay routes show --relay https://relay.example.net --limit 50
acp relay ops stats --relay https://relay.example.net
acp relay ops failures --relay https://relay.example.net --limit 50
```

JSON output:

```bash
acp --json discover get --agent-id agent:ricardo.chess@demo
```

Local demo-only HTTP example (explicit override):

```bash
acp --allow-insecure-http relay status --relay http://localhost:8080
```

Optional HTTPS + mTLS example:

```bash
acp \
  --config ~/.acp/config.json \
  --mtls-enabled \
  --ca-file ./tls/ca.pem \
  --cert-file ./tls/client-cert.pem \
  --key-file ./tls/client-key.pem \
  transport probe --agent-id agent:john.chess@demo
```

Optional Vault-backed key-provider selection:

```bash
export VAULT_TOKEN="..."
acp \
  --key-provider vault \
  --vault-url https://vault.example.net \
  --vault-path secret/data/acp/identities \
  --json config show
```

Config validation:

```bash
acp config show
acp config validate
```

## Security Notes

- Private keys are never printed by default.
- Identity verification uses existing SDK identity verification logic.
- Discovery uses existing SDK discovery order (cache, `.well-known`, relay/directory hints).
- No insecure identity bypass is added in this phase.
- `acp message capabilities` reports non-error no-response outcomes explicitly.
- HTTPS is the default for HTTP-based ACP paths.
- Local/dev/demo `http://` use requires explicit `--allow-insecure-http`.
- HTTP mTLS is optional and enterprise-focused; ACP core protocol semantics are unchanged.
- For local/self-signed mTLS testing, set `ca_file` to your local CA bundle and keep `allow_insecure_tls=false` by default.
