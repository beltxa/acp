# ACP Enterprise Scope

This repository ships the public ACP protocol layer (`sdks`, `cli`, `relay-dev`, examples, demos).

Enterprise relay capabilities are private and out of scope for `relay-dev`.

## Private Enterprise Features

The following are enterprise-only and must not be implemented in `relay-dev`:

- Identity governance
  - identity lifecycle and governance workflows
  - trust registry and revocation control
  - cross-organisation trust mapping
- Federation policy control
  - organisation/agent policy decisions
  - capability and routing constraints
  - trust-zone policy management
- Audit and compliance platform
  - audit pipelines and compliance exports
  - forensic/non-repudiation reporting services
- Operational platform
  - HA orchestration
  - multi-region control plane
  - failover/load-balancer strategy management
- Observability platform
  - central tracing backends
  - behaviour analytics and anomaly services
- Managed ACP network control plane

## `relay-dev` Boundary Contract

`relay-dev` is limited to protocol correctness and developer workflows:

- ACP message forwarding
- identity document resolution for routing
- transport delivery (HTTP and optional AMQP fallback)
- local store-and-forward retries

`relay-dev` must reject enterprise-only configuration when requested via environment variables.
