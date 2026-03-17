# John Minimal Demo Package

This package is the minimum John-side bundle.

Included:

- `config/john.chess.yaml`
- `identities/john/agent_john.chess_demo/identity.json`
- `identities/john/agent_john.chess_demo/identity_document.json`
- `identities/john/discovery_cache.json` (includes Ricardo public identity seed)

Not included:

- Ricardo private keys
- relay operator scripts
- full repo assets

## John commands

Direct stage run:

```bash
acp \
  --storage-dir identities/john \
  agent run \
  --agent-id agent:john.chess@demo \
  --transport direct \
  --port 8088
```

Relay stage run:

```bash
acp \
  --storage-dir identities/john \
  agent run \
  --agent-id agent:john.chess@demo \
  --transport relay \
  --port 8088 \
  --relay http://localhost:8080
```
