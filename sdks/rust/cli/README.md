# ACP Rust CLI (`acp-cli`)

Minimal Rust command-line companion for the ACP Rust SDK.

## Build

```bash
cargo build --manifest-path sdks/rust/cli/Cargo.toml
```

## Usage

```bash
cargo run --manifest-path sdks/rust/cli/Cargo.toml -- --help
```

### Create identity

```bash
cargo run --manifest-path sdks/rust/cli/Cargo.toml -- identity create \
  --agent-id agent:rust.sender@localhost:9301 \
  --storage-dir .acp-data
```

