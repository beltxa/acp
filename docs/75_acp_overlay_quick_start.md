# ACP Overlay Quick Start

Overlay mode allows existing HTTP services to adopt ACP with minimal changes.

---

## Flask Example (Thin Wrapper)

```python
from flask import Flask, jsonify, request
from acp.agent import Agent
from acp.overlay_framework import OverlayFrameworkRuntime, register_flask_overlay_routes

app = Flask(__name__)
agent = Agent.load_or_create(
    "agent:overlay.flask@localhost:9020",
    endpoint="http://localhost:9020/orders",
    discovery_scheme="http",
    allow_insecure_http=True,  # local/demo only
)
runtime = OverlayFrameworkRuntime.create(
    agent=agent,
    base_url="http://localhost:9020",
    business_handler=lambda payload: {"received": payload},
    passthrough_handler=lambda body: {"received": body},
)
register_flask_overlay_routes(app, runtime=runtime)

@app.post("/orders")
def orders():
    body = request.get_json(silent=True)
    response = runtime.handle_message_body(body)
    return jsonify(response.body), response.status_code
```

---

## Spring Boot Example (Thin Wrapper)

```java
private final OverlayHttpRuntime overlay = new OverlayHttpRuntime(
    agent,
    "https://agent.example.com",
    payload -> Map.of("received", payload),
    body -> Map.of("received", body)
);

@PostMapping("/api/v1/acp/messages")
public ResponseEntity<Map<String, Object>> inbound(@RequestBody Map<String, Object> rawMessage) {
    OverlayHttpRuntime.HttpOverlayResponse response = overlay.handle(rawMessage);
    return ResponseEntity.status(response.statusCode()).body(response.body());
}

@GetMapping("/.well-known/acp")
public ResponseEntity<Map<String, Object>> wellKnown() {
    return ResponseEntity.ok()
        .header("Cache-Control", overlay.wellKnownHeaders().get("Cache-Control"))
        .body(overlay.wellKnownDocument());
}
```

---

## Decorator Convenience (Python)

For small route-level wrapping where your framework handler parses JSON and passes a payload dict:

```python
from acp.overlay_framework import acp_overlay_inbound

@acp_overlay_inbound(config={"agent": agent})
def wrapped_orders(payload):
    return {"received": payload}

# in your route:
# result = wrapped_orders(body_dict)
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
  "identity_document": "https://agent.example.com/api/v1/acp/identity",
  "transports": {
    "http": {
      "endpoint": "https://agent.example.com/api/v1/acp/messages"
    }
  },
  "version": "1.0",
  "security_profile": "https"
}
```

The endpoint is advisory bootstrap metadata only. Identity-document and message verification remain authoritative.

---

## Send an ACP Message

```python
from acp.overlay_framework import OverlayClient

client = OverlayClient.create(agent=agent)
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

Local/demo `http://` endpoints require explicit insecure override flags.
