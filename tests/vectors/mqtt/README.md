# ACP MQTT Interoperability Fixtures (Frozen v1)

This directory contains the frozen MQTT interoperability vectors for ACP SDKs.

Scope:
- Python SDK
- Java SDK

Rules:
- `serialized_body` is the canonical ACP message body for the fixture.
- `transport_metadata.user_properties` mirrors ACP envelope metadata and is non-canonical.
- Topic naming must remain deterministic (`acp/agent/<normalized_agent_identifier>`).
- Any change to envelope/protected field names, wrapped key structure, topic format, or metadata mirroring is protocol-impacting.

Required fixture files:
- `python_to_python_send.json`
- `java_to_python_send.json`
- `python_to_java_send.json`
- `multi_recipient_send_B.json`
- `multi_recipient_send_C.json`
- `multi_recipient_send_D.json`
- `duplicate_delivery_case.json`
- `ack_example.json`
- `fail_example.json`
