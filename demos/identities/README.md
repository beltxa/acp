# Demo Identities

This directory stores pre-generated ACP identities for the John demo.

- `john/` contains local identity material for `agent:john.chess@demo`
- `ricardo/` contains local identity material for `agent:ricardo.chess@demo`

Each identity storage directory follows ACP runtime layout:

- `<storage>/<sanitized-agent-id>/identity.json` (private + public key material)
- `<storage>/<sanitized-agent-id>/identity_document.json` (signed public identity document)

Security notes:

- Do not paste `identity.json` contents into chat, tickets, or slides.
- Share only `identity_document.json` when public identity exchange is needed.
- These keys are for demo use only.
