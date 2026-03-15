# ACP Framework Overlay Freeze Note
Version: Draft v1

## Purpose
Freeze the initial framework overlay wrapper surface so developer APIs remain stable while adoption begins.

---

## Python Overlay Surface

Inbound decorator:

```python
@acp_overlay_inbound(config)
def handler(payload):
    ...
```

Outbound helper:

```python
client.send_acp(target_url, payload)
```

Supported frameworks:

- Flask
- FastAPI / ASGI

---

## Java Overlay Surface

Inbound runtime helper:

```
OverlayHttpRuntime.handle(request, handler, config)
```

Outbound helper:

```
overlayClient.sendAcp(targetBaseUrl, payload)
```

Primary target framework:

- Spring Boot / servlet-based applications

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

---

## Security Rules

Overlay wrappers must preserve:

- ACP identity verification
- payload encryption
- message signatures
- HTTPS-first transport policy
- optional mTLS support

Overlay mode must never weaken protocol security guarantees.

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