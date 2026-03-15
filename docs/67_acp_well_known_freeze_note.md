# ACP Well-Known Model Freeze Note

Date: 2026-03-15  
Status: Frozen for current ACP HTTP discovery model

## 1. Canonical Endpoint

- Endpoint path: `/.well-known/acp`
- Published over HTTP(S) by ACP-capable HTTP agents.
- Consumers may start from base URL and derive this path.

## 2. Frozen Response Shape

Required fields:

- `agent_id` (string, valid ACP agent identifier)
- `identity_document` (string URL reference only)
- `transports` (object/map)
- `version` (string, must be `"1.0"`)

Optional fields:

- `security_profile` (string, one of: `http`, `https`, `mtls`, `https+mtls`)
- `capabilities` (array of capability names)

Transport-hint validation rules:

- each `transports.<name>` value must be an object
- optional `endpoint` must be an absolute `http(s)` URL
- optional `security_profile` must use the allowed set above

## 3. Explicit Decision: `identity_document`

`identity_document` is now frozen as URL-reference-only:

- allowed: absolute `http(s)` URL
- allowed: root-relative path (resolved against well-known source URL)
- not allowed: embedded identity document object
- not allowed: non-http(s) URL schemes

This decision closes prior ambiguity and is now enforced in SDK/relay validation.

## 4. Security and Authority Rules

- Well-known metadata is discovery input only.
- Trust root remains the ACP identity document signature verification.
- Well-known metadata must not contain secrets/private keys.
- HTTPS-first posture remains default; HTTP requires explicit insecure override per runtime policy.

## 5. Cache Behavior Expectations

- Clients may cache well-known metadata briefly (for example, honoring `Cache-Control` where present).
- Cached metadata must be treated as advisory and revalidated against identity-document verification.
- Endpoint/hint changes are expected; consumers should refresh periodically.

## 6. Authoritative vs Advisory

Authoritative:

- identity document signature verification
- identity document validity (`valid_until`)

Advisory:

- transport hints in well-known metadata
- top-level security profile hints

## 7. Implementation Impact

Frozen-model enforcement updated in:

- `acp-sdk-python/acp/well_known.py`
- `acp-sdk-python/acp/discovery.py`
- `acp-sdk-java/src/main/java/org/acp/client/DiscoveryClient.java`
- `acp-relay/routing.py`

## 8. Fixtures and Tests Added/Updated

Fixtures:

- `tests/vectors/well_known/valid_basic.json`
- `tests/vectors/well_known/invalid_missing_agent_id.json`
- `tests/vectors/well_known/invalid_missing_version.json`
- `tests/vectors/well_known/invalid_identity_document_type.json`
- `tests/vectors/well_known/invalid_identity_document_relative_path.json`
- `tests/vectors/well_known/invalid_identity_document_url.json`
- `tests/vectors/well_known/invalid_transports_type.json`
- `tests/vectors/well_known/invalid_transport_hint_shape.json`
- `tests/vectors/well_known/invalid_transport_endpoint_type.json`
- `tests/vectors/well_known/invalid_transport_endpoint_url.json`
- `tests/vectors/well_known/invalid_version.json`
- `tests/vectors/well_known/invalid_security_profile.json`
- `tests/vectors/well_known/malformed_json.txt`

Tests:

- `acp-sdk-python/tests/test_well_known_validation.py`
- `acp-sdk-python/tests/test_well_known_discovery.py`
- `acp-relay/tests/test_well_known_resolver.py`
- `acp-sdk-java/src/test/java/org/acp/client/DiscoveryClientWellKnownTest.java`
