# ACP HTTPS Hardening Stage 2 Checklist

Version: Stage 1 planning artifact

## Scope Guardrails

- no ACP core message/identity semantics redesign
- no AMQP/MQTT/Kafka/JMS/P2P transport redesign in this pass
- HTTP-based paths become HTTPS-first by default
- local/dev/demo HTTP exceptions remain available by explicit configuration

## 1. Runtime Transport Behavior

Python SDK + Java SDK + Python relay HTTP paths:

1. Treat `https://` as default for HTTP-based endpoint usage.
2. Detect `http://` endpoint/hint use at configuration/selection time.
3. If `allow_insecure_http=false`, reject insecure HTTP in non-local contexts.
4. If `allow_insecure_http=true`, allow but emit explicit warning.
5. Keep existing demo/local flow working when insecure override is explicitly enabled.
6. Keep TLS certificate verification enabled by default for HTTPS.
7. Support optional insecure TLS mode only via explicit override.

## 2. CLI / Config Validation Behavior

1. Add validation pass that inspects:
   - direct endpoint hints
   - relay hints
   - discovery scheme/hints
2. Default behavior:
   - warn or fail on insecure HTTP (implementation profile decision: strict or warning mode)
3. Explicit override:
   - allow insecure HTTP only when user opts in
4. Display secure/insecure status in relevant CLI outputs:
   - `agent status`
   - `transport list`
   - `transport probe`
   - `relay status` where endpoint metadata is shown

## 3. Discovery / Registration Hint Generation

1. Ensure generated service hints prefer `https://` for HTTP-based hints.
2. Preserve current hint schema; do not redesign identity document fields.
3. If user provides `http://` hint:
   - require explicit insecure override
   - annotate warning in CLI result
4. Preserve existing relay/discovery resolution order and semantics.

## 4. Demo / Config Updates

1. Keep local demo assets functional with explicit insecure exception path.
2. Ensure docs clearly mark:
   - local/demo HTTP usage as exception
   - HTTPS as production-style default
3. Keep demo bootstrap scripts unchanged in behavior unless needed for explicit warning plumbing only.

## 5. Tests to Add

1. Config validation tests:
   - insecure HTTP rejected/warned by default
   - insecure HTTP allowed with override
2. Discovery/registration tests:
   - HTTPS hints accepted cleanly
   - HTTP hints require override
3. CLI behavior tests:
   - secure/insecure transport visibility in output
   - warning text presence when insecure overrides enabled
4. Demo-safety tests:
   - local/demo workflows still pass with explicit insecure flag

## 6. Recommended Minimum Flags

- `allow_insecure_http` (bool, default `false`)
- `allow_insecure_tls` (bool, default `false`)
- `ca_file` (optional path)

Optional if needed later:

- `cert_file` (optional path)
- `key_file` (optional path)

## 7. Stage 2 Rollout Safety Notes

1. Apply strict defaults only after explicit demo/local override path is wired.
2. Keep fallback path for current demo:
   - local `http://localhost` with explicit insecure enablement
3. Avoid hidden fallback from HTTPS to HTTP.
