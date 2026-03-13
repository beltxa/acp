from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query

from routing import RelayDiscoveryResolver, RelayRouter
from storage import MessageStore
from validation import is_expired, validate_envelope


def register_routes(
    app: FastAPI,
    *,
    router: RelayRouter,
    resolver: RelayDiscoveryResolver,
    store: MessageStore,
) -> None:
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/messages")
    def send_message(message: dict[str, Any]) -> dict[str, Any]:
        envelope = message.get("envelope")
        if not isinstance(envelope, dict):
            raise HTTPException(status_code=400, detail="Missing message envelope")
        errors = validate_envelope(envelope)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        if is_expired(str(envelope["expires_at"])):
            raise HTTPException(status_code=400, detail="Message is expired")

        outcomes = router.route_message(message)
        message_id = str(envelope["message_id"])
        operation_id = str(envelope["operation_id"])
        store.save(
            message_id=message_id,
            operation_id=operation_id,
            message=message,
            outcomes=outcomes,
        )
        return {
            "message_id": message_id,
            "operation_id": operation_id,
            "outcomes": outcomes,
        }

    @app.get("/messages/{message_id}")
    def get_message(message_id: str) -> dict[str, Any]:
        stored = store.get(message_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Message not found")
        return stored

    @app.get("/pending-deliveries")
    def pending_deliveries(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        return {
            "pending_count": store.pending_count(),
            "items": store.list_pending(limit=limit),
        }

    @app.post("/pending-deliveries/process")
    def process_pending_deliveries(limit: int = Query(20, ge=1, le=500)) -> dict[str, Any]:
        processed = router.process_pending_deliveries(limit=limit)
        return {
            "processed_count": len(processed),
            "outcomes": processed,
            "pending_count": store.pending_count(),
        }

    @app.get("/discover")
    def discover(agent_id: str = Query(..., min_length=1)) -> dict[str, Any]:
        try:
            identity_document = resolver.resolve(agent_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"identity_document": identity_document}

    @app.post("/identities")
    def register_identity(body: dict[str, Any]) -> dict[str, str]:
        identity_document = body.get("identity_document")
        if not isinstance(identity_document, dict):
            raise HTTPException(status_code=400, detail="Expected identity_document object")
        try:
            resolver.register_identity_document(identity_document)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "registered", "agent_id": identity_document["agent_id"]}
