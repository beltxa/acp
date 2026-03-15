
# ACP Completion Checklist and Ordered Backlog

Version: Draft v1

## Purpose

This document gives a practical ordered checklist so ACP work can be completed and tracked without losing deferred items.

It is based on the current document set and implementation state.

---

## A. Core ACP Baseline

These areas appear implemented and documented.

- [x] Core protocol draft and summary
- [x] Identity model
- [x] Discovery model
- [x] Capability negotiation
- [x] Agent interaction patterns
- [x] Relay architecture baseline
- [x] Reference architecture and implementation plans

---

## B. Transport Bindings

These areas appear implemented and validated at the current baseline.

- [x] Transport abstraction freeze
- [x] AMQP binding specification
- [x] AMQP implementation
- [x] AMQP fixtures freeze
- [x] AMQP conformance checklist
- [x] MQTT binding specification
- [x] MQTT implementation
- [x] Transport invariants

---

## C. CLI and Demo Operations

These areas appear implemented.

- [x] CLI v1 specification
- [x] CLI implementation brief
- [x] CLI command surface
- [x] Identity / discovery / registration / messaging commands
- [x] Agent / transport / relay inspection commands
- [x] Demo runbook / commands / topology / fallback plan
- [x] Quick start

---

## D. HTTP/HTTPS/mTLS Security Hardening

These areas appear implemented.

- [x] HTTPS-first hardening
- [x] HTTPS validation / explicit insecure overrides
- [x] Optional HTTP mTLS profile
- [x] Python mTLS support
- [x] Java mTLS/trust-store parity
- [x] Enterprise security deployment profile

---

## E. Enterprise Key Custody and Trust Model

These areas appear implemented at the current level.

- [x] Key and certificate management model
- [x] Key provider abstraction
- [x] Python local + Vault providers
- [x] Java local + Vault providers
- [x] Agent identity vs endpoint trust model
- [x] Security and trust architecture overview
- [x] Enterprise deployment reference pack

---

## F. Adoption and Positioning Architecture

These areas are documented.

- [x] Overlay adoption model
- [x] Architecture and adoption overview
- [x] One-page protocol overview
- [x] Ecosystem diagram
- [x] Economic model
- [x] Architecture diagrams

---

## G. Well-Known Discovery

These areas appear implemented or in immediate freeze scope.

- [x] Well-known endpoint specification
- [x] Well-known implementation package / brief / prompt
- [x] Well-known implementation pass
- [x] Freeze the well-known model
- [x] Add explicit malformed well-known metadata fixtures/tests
- [x] Decide whether `identity_document` remains flexible or becomes URL-only in a later tightening pass
- [x] Add well-known conformance/freeze note

---

## H. Overlay Adapter Pass

These are the next major items.

- [x] Overlay adoption model documented
- [x] Overlay adapter model documented
- [x] Overlay implementation brief prepared
- [x] Implement inbound HTTP overlay adapter
- [x] Implement outbound HTTP overlay adapter
- [x] Integrate overlay pass with well-known discovery
- [x] Add overlay examples and demo assets
- [x] Add overlay tests
- [x] Generate overlay results document

---

## I. Enterprise Consolidation / Verification

These may already be mostly complete, but should be explicitly frozen if not yet done.

- [x] Confirm Python / Java / Relay config-schema parity in one freeze note
- [x] Freeze enterprise profile config examples
- [x] Add cross-language enterprise-profile security test summary
- [x] Record final enterprise profile consolidation results if not already frozen sufficiently

---

## J. Future Enterprise Enhancements

Important, but not required before overlay work.

- [ ] AWS KMS provider
- [ ] Other cloud secret providers
- [ ] Token lifecycle / rotation automation
- [ ] Remote signing / unwrap mode
- [ ] PKI issuance / revocation orchestration
- [ ] Secret-vault integration hardening beyond Vault v1 support

---

## K. Future Protocol Enhancements

Useful later, but not current blockers.

- [ ] Sender descriptor envelope extension
- [ ] Non-HTTP discovery bootstrap patterns
- [ ] AMQP/MQTT enterprise mutual-auth profiles if needed
- [ ] Additional transport bindings beyond the current set

---

## Recommended Execution Order

### Close current architecture cleanly
1. Freeze the well-known model
2. Overlay adapter design pass
3. Overlay adapter implementation pass
4. Overlay examples / tests / result document

### Then return to enterprise expansion
5. Enterprise consolidation freeze note if needed
6. AWS KMS provider
7. Cloud/provider expansion

### Then protocol refinements
8. Sender descriptor extension
9. additional trust/profile refinements
10. future transports if still valuable

---

## Working Rule

Nothing should be left as a vague “later.”

Every deferred item should either be:
- checked off as done
- actively scheduled
- or explicitly marked as intentionally postponed
