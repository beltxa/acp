
# ACP Well-Known Endpoint Specification
Version: Draft v1

## Purpose

This document defines the **ACP Well-Known Endpoint**, a lightweight discovery mechanism that allows any ACP-capable agent to publish its identity and communication hints in a standard way.

The goal is to enable **zero-configuration discovery** and make ACP easy to adopt in overlay mode.

The endpoint follows the same design philosophy as other widely adopted standards such as:

- `/.well-known/openid-configuration` (OpenID Connect)
- `/.well-known/security.txt`
- `/.well-known/oauth-authorization-server`

By standardizing this endpoint, ACP agents become **self-describing** and immediately discoverable.

---

# 1. Endpoint Location

Every ACP-capable agent should expose the following endpoint:

```
/.well-known/acp
```

Example:

```
https://agent.example.com/.well-known/acp
```

This endpoint returns a JSON document describing the agent.

---

# 2. Basic Response Structure

Example response:

```json
{
  "agent_id": "agent:ricardo.chess@demo",
  "identity_document": "https://agent.example.com/identity.json",
  "transports": {
    "http": {
      "endpoint": "https://agent.example.com/acp"
    },
    "relay": {
      "endpoint": "https://relay.example.com"
    }
  },
  "security_profile": "https",
  "version": "1.0"
}
```

---

# 3. Required Fields

| Field | Description |
|------|-------------|
| agent_id | The ACP logical identity of the agent |
| identity_document | URL of the ACP identity document |
| transports | Map of supported transport bindings |
| version | ACP protocol version supported |

---

# 4. Optional Fields

| Field | Description |
|------|-------------|
| security_profile | Indicates transport security requirements |
| capabilities | Supported ACP capability hints |
| relay_hint | Preferred relay infrastructure |
| discovery | Alternate discovery service endpoints |
| metadata | Additional non-critical information |

Example:

```json
{
  "capabilities": [
    "capabilities_request",
    "relay_routing",
    "multi_recipient_send"
  ]
}
```

---

# 5. Transport Hints

The `transports` section advertises how the agent can be reached.

Example:

```json
{
  "transports": {
    "http": {
      "endpoint": "https://agent.example.com/acp"
    },
    "amqp": {
      "broker": "amqp://broker.example.com",
      "routing_key": "agent.ricardo.chess"
    },
    "mqtt": {
      "broker": "mqtt://broker.example.com",
      "topic": "agent/ricardo/chess"
    }
  }
}
```

These hints do **not override discovery policies**. They provide guidance to clients.

---

# 6. Security Considerations

The well-known endpoint should:

- be served over HTTPS in production
- return only **public metadata**
- not expose private keys or secrets
- allow identity verification using the referenced identity document

Clients should verify:

1. TLS endpoint trust
2. ACP identity document signatures
3. compatibility with supported transports

---

# 7. Caching Behavior

Responses may include caching headers such as:

```
Cache-Control: max-age=300
```

Clients should refresh periodically to detect endpoint migrations.

---

# 8. Relationship to Discovery Services

The well-known endpoint supports **overlay adoption**.

Overlay mode:
```
client → /.well-known/acp → endpoint hints
```

Enterprise mode:
```
client → discovery registry → agent metadata
```

Both mechanisms may coexist.

---

# 9. Migration and Mobility

Because the endpoint exposes **agent identity separately from endpoint location**, agents can move infrastructure without changing their identity.

Example lifecycle:

1. Agent runs locally
2. Agent migrates to cloud
3. Endpoint hints update
4. Agent identity remains unchanged

This enables infrastructure mobility.

---

# 10. Strategic Value

The well-known endpoint enables:

- frictionless experimentation
- automatic agent discovery
- overlay adoption on existing services
- easier integration with web infrastructure

This feature can make ACP spread organically in the same way HTTP endpoints did.

---

# Summary

The ACP Well-Known Endpoint allows agents to publish their identity and communication hints using a simple HTTP endpoint.

This makes ACP:

- easier to adopt
- easier to discover
- easier to integrate into existing systems

while preserving ACP’s security and identity guarantees.
