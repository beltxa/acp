# ACP Go SDK (`acp-sdk-go`)

Internal Go implementation of ACP with parity-oriented coverage for:

- ACP message model, envelope/protected payload serialization
- identity creation and signed identity document verification
- direct HTTP transport (HTTPS-first), relay hints, discovery cache, and `/.well-known/acp`
- AMQP and MQTT transport clients (directed delivery mode)
- duplicate-tolerant inbound handling with terminal `ACK`/`FAIL` behavior
- HTTPS hardening + optional mTLS profile + key-provider abstraction (`local`, `vault`)
- overlay adapters for wrapping existing HTTP handlers

## Build and test

```bash
go test ./...
```

The test suite validates shared ACP vectors under:

- `../tests/vectors/amqp`
- `../tests/vectors/mqtt`
- `../tests/vectors/security`
- `../tests/vectors/well_known`

## Notes

- HTTP paths are HTTPS-first by default. `http://` requires `allow_insecure_http = true`.
- mTLS remains optional (`mtls_enabled = true`) and requires `cert_file` + `key_file`.
- Vault integration is intentionally minimal for internal enterprise testing.
