from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query

from routing import RelayDiscoveryResolver, RelayRouter
from storage import MessageStore
from validation import is_expired, validate_envelope


def _identity_summary(identity_document: dict[str, Any]) -> dict[str, Any]:
    service = identity_document.get("service", {})
    capabilities = identity_document.get("capabilities", {})
    return {
        "agent_id": identity_document.get("agent_id"),
        "trust_profile": identity_document.get("trust_profile"),
        "valid_until": identity_document.get("valid_until"),
        "service": {
            "direct_endpoint": service.get("direct_endpoint") if isinstance(service, dict) else None,
            "relay_hints": service.get("relay_hints", []) if isinstance(service, dict) else [],
            "amqp": service.get("amqp") if isinstance(service, dict) else None,
            "mqtt": service.get("mqtt") if isinstance(service, dict) else None,
        },
        "capabilities": {
            "transports": capabilities.get("transports", []) if isinstance(capabilities, dict) else [],
            "supports": capabilities.get("supports", {}) if isinstance(capabilities, dict) else {},
        },
    }


def _pending_route_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "pending_id": record.get("pending_id"),
        "message_id": record.get("message_id"),
        "operation_id": record.get("operation_id"),
        "recipient": record.get("recipient"),
        "endpoint": record.get("endpoint"),
        "attempts": record.get("attempts"),
        "next_attempt_at": record.get("next_attempt_at"),
        "reason_code": record.get("reason_code"),
        "detail": record.get("detail"),
        "created_at": record.get("created_at"),
    }


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

    @app.get("/status")
    def status() -> dict[str, Any]:
        return {
            "status": "ok",
            "relay_version": app.version,
            "registry_count": len(resolver.registry),
            "cache_count": len(resolver.cache),
            "store": {
                "messages_total": store.message_count(),
                "pending_deliveries_total": store.pending_count(),
            },
            "routing": router.routing_snapshot(),
        }

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

    @app.get("/registry")
    def list_registry(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        items = resolver.list_registered_identity_documents(limit=limit)
        return {
            "count": len(items),
            "items": [_identity_summary(item) for item in items],
        }

    @app.get("/registry/{agent_id}")
    def show_registry_entry(agent_id: str) -> dict[str, Any]:
        identity_document = resolver.get_registered_identity_document(agent_id)
        if identity_document is None:
            raise HTTPException(status_code=404, detail="Registry entry not found")
        return {
            "identity_document": identity_document,
            "summary": _identity_summary(identity_document),
        }

    @app.get("/routes")
    def show_routes(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        pending = store.list_pending(limit=limit)
        return {
            "routing": router.routing_snapshot(),
            "pending_count": store.pending_count(),
            "pending": [_pending_route_summary(item) for item in pending],
        }

    @app.get("/ops/stats")
    def ops_stats() -> dict[str, Any]:
        return {
            "status": "ok",
            "registry_count": len(resolver.registry),
            "cache_count": len(resolver.cache),
            "routing": router.routing_snapshot(),
            "store": store.stats(),
        }

    @app.get("/ops/failures")
    def ops_failures(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        items = store.list_failure_outcomes(limit=limit)
        return {
            "count": len(items),
            "items": items,
        }
