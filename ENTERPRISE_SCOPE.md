# ACP Enterprise Scope

This file defines the public/private boundary for ACP relay capabilities in this repository.

## Public Scope (`relay-dev`)

`relay-dev` is the public developer relay for protocol correctness:

- ACP message forwarding
- identity document resolution for routing
- transport delivery (HTTP and optional AMQP fallback)
- local store-and-forward retries

Boundary principle:

`relay-dev` may verify protocol truth, but it may not make enterprise trust/governance decisions.

## Private Scope (Enterprise Relay)

The following remain private and out of scope for this public repository:

- Identity governance layer
  - identity lifecycle management
  - trust registry and revocation mechanisms
  - cross-organisation trust mapping
- Federation policy engine
  - org/agent communication policy decisions
  - capability and routing constraints
  - trust-zone policy controls
- Audit and compliance layer
  - audit pipelines and compliance exports
  - forensic/non-repudiation reporting
- Operational platform
  - HA orchestration
  - multi-region routing/control plane
  - failover and load-balancing control
- Observability platform
  - tracing backends
  - behaviour analytics and anomaly services
- Managed ACP network control plane

## Enforcement Rule in Public Repo

`relay-dev` must reject enterprise-only configuration and modes at startup.
Boundary tests in `relay-dev/tests` must verify this behavior and verify that enterprise-only relay surface is not exposed.
