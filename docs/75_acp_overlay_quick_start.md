# ACP Overlay Quick Start

Overlay mode allows existing HTTP services to adopt ACP with minimal changes.

---

## Flask Example

Existing endpoint:

```python
from flask import Flask
app = Flask(__name__)

@app.route("/hello", methods=["POST"])
def hello():
    return {"message": "Hello"}
```

Add ACP overlay:

```python
from acp.overlay import acp_overlay_inbound

@app.route("/hello", methods=["POST"])
@acp_overlay_inbound(config="agent.yaml")
def hello(payload):
    return {"received": payload}
```

---

## Spring Boot Example

Existing controller:

```java
@PostMapping("/hello")
public ResponseEntity<?> hello(@RequestBody Map<String,Object> payload) {
    return ResponseEntity.ok(payload);
}
```

Add ACP overlay runtime:

```java
@PostMapping("/hello")
public ResponseEntity<?> hello(HttpServletRequest request) {
    return OverlayHttpRuntime.handle(request, payload -> {
        return Map.of("received", payload);
    });
}
```

---

## Discover the Agent

ACP agents expose a well-known discovery endpoint:

```
GET https://agent.example.com/.well-known/acp
```

Example response:

```json
{
  "agent_id": "agent:demo.service",
  "transports": {
    "http": {
      "endpoint": "https://agent.example.com/acp"
    }
  },
  "version": "1.0"
}
```

---

## Send an ACP Message

```python
client.send_acp("https://agent.example.com", {"action": "ping"})
```

The client will:

1. Fetch `/.well-known/acp`
2. Validate the agent identity
3. Send an encrypted ACP message

---

## Security

Overlay mode still enforces:

- identity verification
- message signatures
- payload encryption
- HTTPS-first transport policy