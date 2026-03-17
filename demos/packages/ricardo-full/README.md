# Ricardo Full Demo Package

This package is the Ricardo/operator-side bundle.

Included:

- `config/ricardo.chess.yaml`
- `identities/ricardo/...` (local private/public identity material)
- `relay/relay.demo.yaml`
- `relay/.env.example`
- `scripts/start_demo.sh`
- `scripts/prewarm_registry.sh`

Use this package to:

1. run Ricardo locally in direct or relay mode
2. start the demo relay
3. pre-warm relay registration/discovery
4. apply Ricardo cloud endpoint updates for stage 3

Security:

- keep `identities/ricardo/.../identity.json` private
- share only Ricardo `identity_document.json` when needed
