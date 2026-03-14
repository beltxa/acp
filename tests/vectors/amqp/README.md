# ACP AMQP Interoperability Fixtures (Frozen v1)

This directory contains the frozen AMQP interoperability vectors for ACP.

Scope:
- Python SDK
- Java SDK
- Python relay (AMQP fallback path)

Rules:
- `serialized_body` is the canonical ACP message body for the fixture.
- `transport_metadata.headers` mirrors ACP envelope metadata and is non-canonical.
- Any change to envelope/protected field names, wrapped key structure, header mapping, routing key format, or queue naming must be reviewed as a protocol-impacting change.

Required fixture files:
- `python_to_python_send.json`
- `java_to_python_send.json`
- `python_to_java_send.json`
- `multi_recipient_send_B.json`
- `multi_recipient_send_C.json`
- `multi_recipient_send_D.json`
- `duplicate_delivery_case.json`
- `relay_amqp_fallback_case.json`
- `ack_example.json`
- `fail_example.json`

