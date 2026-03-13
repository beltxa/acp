
# ACP Capability Negotiation – Short Specification

## Overview

ACP capability negotiation determines whether two agents can communicate using compatible protocol versions, crypto suites, transport modes, and feature sets.

ACP prefers capability advertisement over heavy negotiation.

---

## Static Capabilities

Agents may publish stable capability information through discovery or identity documents.

Typical static capabilities include:

- supported protocol versions
- supported crypto suites
- supported transports
- max payload size
- supported profiles

---

## Dynamic Capabilities

Agents may expose dynamic capabilities through an optional `CAPABILITIES` message.

Dynamic capabilities may include:

- temporary relay-only mode
- temporary transport restrictions
- current service state

---

## Capability Object Example

```json
{
  "agent_id": "agent:shipping.bot@companyB.com",
  "protocol_versions": ["1.0"],
  "crypto_suites": [
    "ACP-AES256-GCM+ED25519"
  ],
  "transports": [
    "https",
    "websocket",
    "relay"
  ],
  "supports": {
    "ack": true,
    "fail": true,
    "compensate": true,
    "direct_delivery": true,
    "relay_delivery": true
  },
  "limits": {
    "max_payload_bytes": 1048576
  },
  "profiles": [
    "core",
    "domain_verified"
  ],
  "valid_until": "2026-12-31T00:00:00Z"
}
```

---

## Sender Compatibility Rule

The sender should select the highest mutually compatible:

- protocol version
- crypto suite
- delivery mode

based on:

1. cached capabilities
2. discovery metadata
3. optional `CAPABILITIES` exchange

---

## Mismatch Handling

If compatibility cannot be established, the recipient or receiving infrastructure should return a structured `FAIL`.

Recommended reason codes:

- `UNSUPPORTED_VERSION`
- `UNSUPPORTED_CRYPTO_SUITE`
- `UNSUPPORTED_MESSAGE_CLASS`
- `PAYLOAD_TOO_LARGE`
- `UNSUPPORTED_PROFILE`

---

## Goal

ACP capability negotiation should provide enough information to enable interoperability without introducing heavy session negotiation or complex handshake behavior.
