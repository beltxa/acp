
# ACP John Demo Topology

## Architecture

John Laptop
    Python Chess Agent

        │

    Internet

        │

AWS Relay
Discovery + Routing

        │

Your Machine / AWS
Python Chess Agent

---

## Stage 1
Direct communication:

John Agent → HTTP → Ricardo Agent

Note: this HTTP path is a local/demo exception.
Production-style deployment should use HTTPS for HTTP-based ACP paths.

---

## Stage 2
Relay-assisted:

John Agent → Relay → Ricardo Agent

---

## Stage 3
Cloud-hosted agent:

John Agent → Relay → AWS Ricardo Agent

Identity remains constant across all stages.
