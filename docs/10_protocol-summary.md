# ACP Protocol Summary (Reference v0.1)

This implementation models ACP messages as:

1. Routing envelope (cleartext metadata)
2. Protected payload (encrypted + signed content)

## Envelope

Required fields:

- `acp_version`
- `message_class`
- `message_id`
- `operation_id`
- `timestamp`
- `expires_at`
- `sender`
- `recipients`
- `context_id`
- `crypto_suite`

Optional:

- `correlation_id`
- `in_reply_to`

## Message Classes

Implemented:

- `SEND`
- `ACK`
- `FAIL`
- `CAPABILITIES`
- `COMPENSATE` (structure + transport support)

`ACK` and `FAIL` are terminal protocol responses, and agents do not auto-emit `ACK`/`FAIL` in response to incoming `ACK`/`FAIL`.

## Crypto

Default crypto suite:

- `Ed25519` for signatures
- `X25519` for key agreement/wrapping
- `AES-256-GCM` for payload encryption

Flow:

1. Sender encrypts payload once with a random content key (CEK)
2. Sender wraps CEK per recipient using X25519-derived wrapping keys
3. Sender signs envelope + protected payload metadata
4. Recipient verifies signature and decrypts with its wrapped CEK

## Identity & Discovery

Each identity document includes:

- agent identifier
- public signing/encryption keys
- endpoint hints (`direct_endpoint`, `relay_hints`)
- trust profile
- capabilities
- Ed25519 signature over the document

Discovery order:

1. local cache
2. domain `.well-known/acp/agents/<agent_name>`
3. relay hint lookup (`/discover?agent_id=...`)

## Relay

The reference relay:

- validates envelope fields and expiry
- resolves recipients
- forwards ACP messages unchanged to recipient endpoints
- stores outcomes in-memory
- does not decrypt or mutate payloads
