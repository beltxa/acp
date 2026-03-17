# ACP Rust SDK (`acp`)

Status: `Available from repo`

Rust SDK implementation of ACP message, identity, and transport features.

## Build and test

```bash
cargo check --manifest-path sdks/rust/Cargo.toml
cargo test --manifest-path sdks/rust/Cargo.toml
```

## Example bootstrap

```rust
use acp::{AcpAgent, AcpAgentOptions};

let mut options = AcpAgentOptions::default();
options.allow_insecure_http = true; // local/dev only
let _agent = AcpAgent::load_or_create("agent:rust.demo@localhost:9301", Some(options))?;
# Ok::<(), acp::AcpError>(())
```

## First-run reference

For the shortest end-to-end ACP walkthrough, use:

```bash
./getting-started/quickstart_ping.sh
```
