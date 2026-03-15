
# ACP Overlay Adapter Model

Version: Draft v1

## Purpose

This document defines the ACP Overlay Adapter Model, which explains how ACP can be
introduced into existing systems without requiring those systems to become full ACP-native runtimes.

The overlay model is the next adoption layer after the ACP Well-Known Endpoint.

Its goal is to let teams add ACP semantics to:

- existing HTTP services
- webhooks
- internal APIs
- existing service-to-service calls
- selected broker-backed interactions

with minimal architectural disruption.

---

## 1. Why Overlay Adapters Exist

Many organizations already have service endpoints, handlers, and message flows in place.

They may want ACP benefits such as:

- agent identity
- message signing
- payload encryption
- transport hints
- well-known discovery
- reply routing conventions

without immediately introducing:

- full ACP-native runtimes everywhere
- relay-first architecture
- registry-first discovery
- infrastructure replacement

Overlay adapters provide that bridge.

---

## 2. Overlay Mode vs Native Mode

### Overlay Mode
ACP is layered onto existing service endpoints and handlers.

Typical shape:

```text
Existing Service Endpoint
        +
ACP envelope handling
        +
ACP identity and security
```

### Native Mode
ACP runtime is the primary communication fabric.

Typical shape:

```text
ACP Runtime
  ├ discovery
  ├ transport selection
  ├ relay integration
  └ message lifecycle
```

Overlay mode is for incremental adoption.
Native mode is for full ACP architecture.

---

## 3. Overlay Adapter Concept

An overlay adapter is a thin runtime layer that does one or more of the following:

- wraps an existing inbound HTTP endpoint with ACP request parsing and verification
- wraps an existing outbound call with ACP message construction and signing/encryption
- exposes a self-describing `/.well-known/acp` endpoint
- provides minimal identity and transport metadata
- preserves existing application behavior as much as possible

Overlay adapters should not require a complete re-architecture of the host application.

---

## 4. Inbound Overlay Adapter

An inbound overlay adapter should support:

1. accepting an HTTP(S) request
2. detecting ACP message format
3. validating ACP identity and signatures
4. decrypting ACP payload where appropriate
5. passing the resulting business payload to an existing handler
6. constructing ACP response semantics if needed

Conceptually:

```text
HTTP request
   ↓
Overlay Adapter
   ↓
ACP verify / decrypt
   ↓
Existing application handler
```

This lets an existing service become ACP-capable.

---

## 5. Outbound Overlay Adapter

An outbound overlay adapter should support:

1. taking an existing business payload
2. wrapping it in ACP envelope format
3. signing and encrypting as required
4. using well-known discovery or static hints
5. sending via existing transport

Conceptually:

```text
Existing application call
   ↓
Overlay Adapter
   ↓
ACP envelope / sign / encrypt
   ↓
HTTP(S) or other supported transport
```

This lets an existing service call another service using ACP semantics.

---

## 6. Required Overlay Capabilities

The first overlay pass should focus on HTTP(S) because it is the lowest-friction adoption path.

Required capabilities:

- self-describing `/.well-known/acp`
- inbound ACP-over-HTTP handling
- outbound ACP-over-HTTP sending
- optional static or well-known discovery
- explicit identity configuration
- secure defaults consistent with HTTPS-first ACP

Optional later:

- broker-side overlay adapters
- framework-specific middleware
- service-mesh integration patterns

---

## 7. Design Rules

1. Overlay adapters must not weaken ACP identity or message security semantics.
2. Overlay adapters should reuse existing ACP runtime components wherever possible.
3. Overlay adapters should be thin wrappers, not new protocol implementations.
4. Existing application behavior should be minimally disturbed.
5. Overlay adapters should favor configuration over infrastructure change.
6. Overlay adapters should be compatible with the well-known endpoint model.

---

## 8. Python Overlay Targets

Likely initial overlay targets:

- simple HTTP handler wrapper
- existing ACP demo services
- lightweight WSGI/ASGI-compatible wrapper if practical

Example conceptual API:

```python
wrap_existing_http_handler(handler, agent_config)
send_acp_over_http(target_url, payload, agent_config)
```

---

## 9. Java Overlay Targets

Likely initial overlay targets:

- simple HTTP handler wrapper
- minimal client-side outbound adapter
- compatibility with existing Java agent examples

Example conceptual API:

```java
OverlayInboundAdapter.handle(request, handler, config);
OverlayOutboundAdapter.send(targetUrl, payload, config);
```

---

## 10. Discovery in Overlay Mode

Overlay mode should prefer the simplest discovery ladder:

1. explicit target URL
2. derive `/.well-known/acp`
3. consume transport hints
4. cache useful metadata
5. optionally fall back to richer ACP discovery later

Overlay mode should not require relay or registry on day one.

---

## 11. Security in Overlay Mode

Overlay mode must still respect:

- ACP identity verification
- ACP payload security
- HTTPS-first transport posture
- optional mTLS where configured

Overlay mode is about adoption convenience, not weaker security.

---

## 12. Strategic Value

The overlay adapter model is the practical mechanism that turns ACP from:

- a protocol to adopt later

into:

- a protocol teams can start using immediately on top of what they already run

This directly addresses adoption-friction concerns.

---

## 13. Summary

The ACP Overlay Adapter Model provides a bridge between:

- existing application/service architectures
- full ACP-native runtimes

It should be implemented as a thin, HTTP-first, well-known-aware adapter layer that enables incremental adoption with minimal disruption.
