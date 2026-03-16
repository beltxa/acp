# ACP AMQP Conformance Report (Current Implementation)

Date: 2026-03-13  
Scope: `acp-sdk-python`, `acp-sdk-java`, `acp-relay` in this repository.

Legend:
- `PASS`: implemented and evidenced in code/tests
- `PARTIAL`: implemented in part, ambiguous, or not fully demonstrated end-to-end
- `GAP`: missing or not currently demonstrated

## A. Core ACP Invariants

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| ACP protocol semantics remain unchanged | PASS | `acp-sdk-python/acp/agent.py`, `acp-sdk-java/src/main/java/org/acp/client/AcpAgent.java` |
| ACP identity model remains unchanged | PASS | `acp-sdk-python/acp/identity.py`, `acp-sdk-java/src/main/java/org/acp/client/AgentIdentity.java` |
| ACP discovery model remains unchanged | PASS | `acp-sdk-python/acp/discovery.py`, `acp-sdk-java/src/main/java/org/acp/client/DiscoveryClient.java` |
| ACP encryption remains protocol-layer | PASS | `acp-sdk-python/acp/crypto.py`, `acp-sdk-java/src/main/java/org/acp/client/CryptoSupport.java` |
| ACP payload remains opaque to broker | PASS | AMQP code transports serialized ACP blobs only |

## B. Message Carriage

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Complete ACP message in AMQP body | PASS | `acp-sdk-python/acp/amqp_transport.py`, `acp-sdk-java/src/main/java/org/acp/client/AmqpTransportClient.java`, `acp-relay/amqp_binding.py` |
| AMQP body contains serialized ACP JSON | PASS | same as above (`json.dumps` / `JsonSupport.toJson`) |
| Routing envelope preserved unchanged | PASS | AMQP publishers send ACP message object directly |
| Protected payload preserved unchanged | PASS | AMQP publishers do not mutate `protected` |
| Canonical JSON field names preserved | PASS | fixtures under `tests/vectors/amqp/*.json` |

## C. Header Behavior

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Optional AMQP headers mirror ACP metadata | PASS | `_metadata_headers` and `metadataHeaders` implementations |
| Headers not canonical ACP fields | PASS | inbound AMQP consumers parse body, not headers |
| Missing metadata headers do not break processing | PASS | consumer logic does not require headers |
| Header values consistent with ACP body | PASS | fixture tests in Python/Java/relay validate mapping |

Suggested mirrored headers:
- `acp_version`: PASS
- `acp_message_class`: PASS
- `acp_message_id`: PASS
- `acp_operation_id`: PASS
- `acp_sender`: PASS

## D. Routing Model

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Exchange name configured | PASS | defaults + overrides in AMQP transport clients |
| Queue naming format followed | PASS | `queue_name_for_agent` / `queueNameForAgent` |
| Routing key format followed | PASS | `routing_key_for_agent` / `routingKeyForAgent` |
| One recipient = one AMQP publish operation | PASS | per-recipient AMQP publish in Python/Java sender paths |
| Multi-recipient SEND => one AMQP message per recipient | PASS | AMQP path in Python/Java send loops |
| Broker routing does not change ACP semantics | PASS | transport-only use of broker |

## E. Delivery Semantics

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| At-least-once semantics remain the ACP assumption | PASS | ACP semantics unchanged; AMQP uses ack/nack model |
| Duplicate delivery tolerated | PASS | duplicate tests in Python/Java |
| Recipient deduplicates by `message_id` | PASS | `_processed_message_ids` (Python), `DedupStore` (Java) |
| Exactly-once not assumed | PASS | no exactly-once assumptions in SDK/relay |
| Broker ack/requeue does not override ACP semantics | PASS | SDK consumers now `nack(..., requeue=true)` on handler failure and ACK terminal ACP outcomes |

## F. Crypto and Security

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Signature verifies after AMQP delivery | PASS | inbound verification in Python/Java receive paths |
| Payload decrypts after AMQP delivery | PASS | inbound decrypt in Python/Java receive paths |
| Wrapped keys remain intact | PASS | whole `protected` object carried unchanged |
| Broker does not require decrypted content | PASS | no broker-side decrypt dependency |
| Broker treated as untrusted infrastructure | PASS | relay and SDK treat broker as transport only |

## G. Interoperability

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Python -> Python over AMQP works | PARTIAL | unit coverage uses fake transport; no broker-backed E2E fixture runner |
| Java -> Python over AMQP works | PARTIAL | frozen fixtures added; no automated cross-runtime broker E2E test yet |
| Python -> Java over AMQP works | PARTIAL | frozen fixtures added; no automated cross-runtime broker E2E test yet |
| Multi-recipient AMQP send works | PASS | AMQP per-recipient send tests in Python/Java |
| ACK and FAIL over AMQP work correctly | PASS | AMQP consume helpers now publish generated ACK/FAIL messages back over AMQP sender routes |
| Duplicate behavior correct across languages | PARTIAL | duplicate handling tested per SDK; cross-language duplicate scenario not yet automated |

## H. Relay Behavior

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Relay can use AMQP fallback | PASS | `acp-relay/routing.py` + relay AMQP tests |
| Relay does not alter ACP message body | PASS | relay AMQP publish sends inbound message dict unchanged |
| Relay does not decrypt payload | PASS | no relay decrypt path present |
| Relay preserves recipient routing intent | PARTIAL | relay publishes per recipient, but forwards unchanged multi-recipient body if provided |
| AMQP fallback works when direct unavailable | PASS | relay tests and frozen fallback fixture |

## I. Error Handling

| Checklist Item | Status | Evidence |
| --- | --- | --- |
| Unsupported message produces ACP FAIL | PARTIAL | parse-time unsupported/invalid classes can return structural failure without FAIL response message |
| Invalid signature produces ACP FAIL | PASS | inbound verification failure maps to FAIL |
| Expired message produces ACP FAIL | PASS | expiry validation maps to FAIL |
| Unsupported crypto suite produces ACP FAIL | PASS | crypto-suite validation maps to FAIL |
| Payload-too-large behavior defined | GAP | capability limits exist but explicit payload-size enforcement is not implemented |

## J. Final Acceptance

Current status:
- Required fixtures are now frozen under `tests/vectors/amqp/`
- Core AMQP binding behavior is largely conformant
- Remaining acceptance blockers are demonstration gaps, not ACP-core semantic conflicts

Open mismatches / ambiguities to track:
1. Cross-runtime AMQP E2E (Python<->Java) is not yet automated against a real broker.
2. Payload-too-large enforcement is not explicitly implemented.
3. Relay fallback forwards unchanged bodies; for multi-recipient inputs this can carry recipient lists/wrapped keys for more than one recipient.
