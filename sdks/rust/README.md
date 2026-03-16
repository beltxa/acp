# ACP Rust SDK (`acp-sdk-rust`)

Internal Rust implementation of ACP with parity-oriented coverage for:

- ACP message model, envelope/protected payload serialization
- identity creation and signed identity document verification
- direct HTTP transport (HTTPS-first), relay hints, discovery cache, and `/.well-known/acp`
- AMQP and MQTT transport clients (directed delivery mode)
- duplicate-tolerant inbound handling with terminal `ACK`/`FAIL` behavior
- HTTPS hardening + optional mTLS profile + key-provider abstraction (`local`, `vault`)
- overlay adapters for wrapping existing HTTP handlers

The crate is configured as internal-only:

- `publish = false`
- `license = "UNLICENSED"`

## Build and test

```bash
cargo check
cargo test
```

The test suite includes cross-language fixture validation against shared ACP vectors:

- `tests/vectors/amqp/*`
- `tests/vectors/mqtt/*`
- `tests/vectors/security/*`

## Example bootstrap

```rust
use acp_sdk_rust::{AcpAgent, AcpAgentOptions};

let mut options = AcpAgentOptions::default();
options.allow_insecure_http = true; // local/dev only
let agent = AcpAgent::load_or_create("agent:example@localhost:9001", Some(options))?;
# Ok::<(), acp_sdk_rust::AcpError>(())
```

Overlay outbound demo client (targets an ACP overlay service exposing `/.well-known/acp`):

```bash
ACP_FROM_AGENT_ID=agent:overlay.rust.sender@localhost:9031 \
ACP_TARGET_BASE_URL=http://localhost:9010 \
ACP_ALLOW_INSECURE_HTTP=true \
cargo run --manifest-path acp-sdk-rust/Cargo.toml --example overlay_http_client
```

## Notes

- HTTP paths are HTTPS-first by default. `http://` requires `allow_insecure_http = true`.
- mTLS is optional (`mtls_enabled = true`) and requires `cert_file` + `key_file`.
- Vault integration is intentionally minimal for internal enterprise testing (token + path-based lookup).
