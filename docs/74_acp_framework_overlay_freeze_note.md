# ACP Framework Overlay Freeze Note
Version: Draft v1

## Purpose
Freeze the initial framework overlay wrapper surface so developer APIs remain stable while adoption begins.

---

## Python Overlay Surface (Frozen)

Primary runtime surface:

- `OverlayFrameworkRuntime.create(...)`
- `register_fastapi_overlay_routes(...)`
- `register_flask_overlay_routes(...)`

Frozen convenience surface:

- inbound decorator helper:

```python
@acp_overlay_inbound(config={"agent": agent})
def handler(payload):
    return {"received": payload}
```

- outbound helper:

```python
client = OverlayClient.create(agent=agent)
client.send_acp(target_url, payload)
```

- runtime alias:

```python
runtime.send_acp(target_url, payload)
```

Supported frameworks remain:

- Flask
- FastAPI / ASGI-style integration

---

## Java Overlay Surface (Frozen)

Primary runtime surface:

- `OverlayHttpRuntime.handleMessageBody(...)`
- `OverlayHttpRuntime.wellKnownDocument()`
- `OverlayHttpRuntime.identityDocumentPayload()`
- `OverlayHttpRuntime.sendBusinessPayload(...)`

Frozen convenience surface:

- static inbound helper:

```java
OverlayHttpRuntime.handle(requestBody, handler, config)
```

- outbound helper alias:

```java
overlay.sendAcp(targetBaseUrl, payload)
```

- well-known cache headers helper:

```java
overlay.wellKnownHeaders()
```

Primary target framework remains:

- Spring Boot / servlet-style applications

---

## Well-Known Endpoint Support

Overlay wrappers must expose:

```
GET /.well-known/acp
```

Returning metadata such as:

- agent identity
- transport hints
- security profile
- protocol version

Overlay well-known routes should emit cache headers suitable for short advisory caching:

- `Cache-Control: public, max-age=300`

---

## Security Rules

Overlay wrappers must preserve:

- ACP identity verification
- payload encryption
- message signatures
- HTTPS-first transport policy
- optional mTLS support

Overlay mode must never weaken protocol security guarantees.

Well-known metadata remains advisory bootstrap data only. Trust remains anchored in:

- TLS endpoint validation
- identity document verification
- ACP message signature verification

---

## Deferred Overlay Work

Not included in this freeze:

- non-HTTP overlay transports
- framework-specific package distributions
- sender descriptor message extension
- service mesh integrations

---

## Summary

The overlay wrapper API surface is now frozen to stabilize:

- developer documentation
- framework integrations
- adoption examples
- packaging-level helper imports
