# ACP Mojo Client Specification

## 1. Purpose

This document captures the implemented behavior of the internal Mojo SDK package:

- `acp-sdk-mojo`

The Mojo SDK is intentionally a thin runtime wrapper over the ACP Python SDK so Mojo
applications can use ACP functionality with protocol-correct parity and without duplicating
ACP core logic.

## 2. Package status

- Internal only
- Mojo wrapper + Python bridge model
- Requires Mojo Python interop and ACP Python SDK importability (`import acp`)

## 3. Implemented module surface

Mojo entrypoints (`src/acp_sdk_mojo.mojo`) expose wrapper calls for:

- agent load/create
- send / send_basic / receive
- capabilities request
- well-known build/resolve
- discovery registration helper
- overlay runtime creation
- overlay client send helper
- ACP HTTP payload-shape detection

Python bridge (`python_bridge.py`) provides stable helper functions that map Mojo calls onto
ACP Python runtime APIs (`acp.Agent`, overlay classes, and helper functions).

## 4. Parity model

Parity with other SDKs is achieved by delegation to ACP Python runtime behavior:

- canonical ACP message handling
- cryptographic validation and decryption
- duplicate-tolerant inbound handling with terminal ACK/FAIL behavior
- HTTPS-first transport hardening + optional mTLS profile
- key-provider behavior (`local`, `vault`)
- discovery and `/.well-known/acp` resolution
- AMQP/MQTT support where configured in the Python runtime
- overlay adapter and framework support

## 5. Security and trust posture

- Wrapper does not introduce protocol-semantic changes.
- Identity/signature verification remains in authoritative ACP runtime layer.
- Well-known metadata remains advisory input.
- Bridge code avoids secret logging.

## 6. Configuration fields (effective runtime)

Configuration is passed through to ACP Python `Agent.load_or_create(...)`, including:

- `allow_insecure_http`
- `allow_insecure_tls`
- `mtls_enabled`
- `ca_file`
- `cert_file`
- `key_file`
- key-provider and discovery/transport settings supported by ACP Python runtime

## 7. Out of scope (this pass)

- Native Mojo cryptographic/runtime reimplementation of ACP
- Direct Mojo-native AMQP/MQTT protocol stacks
- Cloud KMS providers beyond existing ACP Python runtime support
- PKI lifecycle automation / rotation / revocation
