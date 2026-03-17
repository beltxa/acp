# ACP TypeScript SDK (`@acp/sdk`)

TypeScript implementation of ACP with parity-oriented coverage:

- ACP envelope/protected message model
- identity creation, signed identity document generation and verification
- direct HTTP transport, relay routing, and `.well-known/acp` discovery support
- AMQP and MQTT transport adapters
- duplicate-tolerant inbound processing with terminal ACK/FAIL behavior
- HTTPS-first validation with optional mTLS config
- key-provider abstraction (`local`, `vault`)
- overlay inbound/outbound adapters and framework runtime helpers

## Build and test

```bash
npm install
npm run lint
npm run test
npm run build
```

Package dry-run:

```bash
npm pack --dry-run
```

Shared-vector parity tests validate against repository fixtures under:

- `../tests/vectors/amqp`
- `../tests/vectors/mqtt`
- `../tests/vectors/security`
- `../tests/vectors/well_known`

## Notes

- HTTP endpoints are HTTPS-first by default; insecure HTTP requires explicit override.
