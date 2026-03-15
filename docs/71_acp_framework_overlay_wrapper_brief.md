# ACP Framework Overlay Wrapper Brief for Codex

Version: Draft v1

## Purpose

Implement framework-integrated ACP overlay wrappers so existing HTTP services can adopt ACP with minimal code changes.

This pass should build on the already implemented overlay adapter foundation and make ACP easier to embed into real services.

Primary targets:

- Python: Flask / FastAPI (or generic WSGI/ASGI-first approach if cleaner)
- Java: Spring Boot / servlet-style HTTP stack

The goal is developer ergonomics, not protocol redesign.

---

## Goal

Provide framework-friendly wrappers/middleware so developers can:

1. expose an existing endpoint through ACP inbound overlay handling
2. send outbound ACP-over-HTTP from existing application logic
3. reuse `/.well-known/acp` bootstrap and existing enterprise security profile
4. avoid converting the whole service into a full ACP-native runtime

---

## Important Rules

1. Do not redesign ACP core semantics.
2. Do not weaken ACP identity verification, message signing, or payload security.
3. Reuse the existing overlay adapter and well-known implementation wherever possible.
4. Keep the first framework pass focused on HTTP(S).
5. Prefer thin wrappers and middleware over heavyweight frameworks or code generation.
6. Keep HTTPS-first, optional mTLS, and key-provider integration compatible with the existing enterprise profile.
7. Finish the pass unless there is a genuine ambiguity or hard blocker.

---

## Scope

### Python
Implement one coherent Python web integration path.

Preferred outcome:
- one generic inbound wrapper for WSGI/ASGI-style services
- framework adapters/examples for Flask and FastAPI

Required capabilities:
- wrap existing inbound handler/route with ACP verification + decrypt path
- expose `/.well-known/acp`
- support outbound ACP-over-HTTP helper usable from application logic
- work with current HTTPS/mTLS/key-provider config model

### Java
Implement one coherent Java web integration path.

Preferred outcome:
- Spring-friendly inbound adapter/filter/interceptor approach
- outbound helper usable from service logic

Required capabilities:
- inbound ACP-over-HTTP handling integrated into Spring/servlet flow
- optional well-known endpoint exposure
- outbound ACP-over-HTTP helper
- compatibility with current HTTPS/mTLS/key-provider model

---

## Required Deliverables

### 1. Python framework integration
Provide:
- inbound wrapper or middleware layer
- outbound helper integration
- at least one Flask example
- at least one FastAPI example if practical, otherwise one generic ASGI example with clear notes

### 2. Java framework integration
Provide:
- Spring-friendly inbound integration
- outbound helper
- at least one Spring Boot example or minimal servlet-style example if cleaner

### 3. Docs / Examples
Create or update docs showing:
- “add ACP to an existing Flask/FastAPI endpoint”
- “add ACP to an existing Spring endpoint”
- “send ACP-over-HTTP from an existing service”
- how `/.well-known/acp` fits into the framework integration story

### 4. Tests
Add focused tests for:
- inbound wrapper behavior
- outbound helper behavior
- well-known endpoint availability in framework context
- HTTPS-first compatibility
- example-level sanity

---

## Design Guidance

### Inbound wrapper pattern
Framework integration should look conceptually like:

```python
@app.post("/existing")
@acp_overlay_inbound(config=...)
def existing_handler(payload):
    ...
```

or:

```java
@PostMapping("/existing")
public ResponseEntity<?> existingHandler(...) {
    ...
}
```

with ACP wrapper/filter handling verification/decrypt before business logic.

### Outbound helper pattern
Application code should be able to do something conceptually like:

```python
client.send_acp(target_base_url, payload)
```

or:

```java
overlayClient.sendAcp(targetBaseUrl, payload);
```

using well-known bootstrap where applicable.

---

## Constraints

Do not implement:
- non-HTTP overlay frameworks
- broad framework matrix beyond Flask/FastAPI and Spring-friendly Java path
- sender descriptor extension
- AWS KMS
- PKI automation
- new transport bindings

---

## Result Document

Generate:

```text
docs/71_acp_framework_overlay_wrapper_results.md
```

It should include:
- files changed
- Python framework wrapper APIs
- Java framework wrapper APIs
- examples added
- tests added/updated
- remaining ergonomics gaps
- recommended next step

---

## Working Style

Be aggressive about making overlay easier to adopt, but keep the implementation thin, reusable, and aligned with the already frozen well-known and enterprise models.
