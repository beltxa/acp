from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from .agent import Agent
from .messages import FailReason
from .overlay import (
    OverlayAdapterError,
    OverlayInboundAdapter,
    OverlayOutboundAdapter,
)


BusinessHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
PassThroughHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
InboundDecoratorHandler = Callable[[dict[str, Any]], dict[str, Any] | None]

WELL_KNOWN_CACHE_CONTROL = "public, max-age=300"

# Runtime alias populated in register_fastapi_overlay_routes when FastAPI is available.
_FastApiRequest = Any


class OverlayFrameworkError(RuntimeError):
    pass


@dataclass(frozen=True)
class OverlayHttpResponse:
    status_code: int
    body: dict[str, Any]


@dataclass
class OverlayFrameworkRuntime:
    agent: Agent
    base_url: str
    inbound_adapter: OverlayInboundAdapter
    outbound_adapter: OverlayOutboundAdapter

    @classmethod
    def create(
        cls,
        *,
        agent: Agent,
        base_url: str,
        business_handler: BusinessHandler,
        passthrough_handler: PassThroughHandler | None = None,
    ) -> "OverlayFrameworkRuntime":
        normalized_base_url = str(base_url or "").strip()
        if not normalized_base_url:
            raise OverlayFrameworkError("base_url is required")
        return cls(
            agent=agent,
            base_url=normalized_base_url.rstrip("/"),
            inbound_adapter=OverlayInboundAdapter(
                agent=agent,
                business_handler=business_handler,
                passthrough_handler=passthrough_handler,
            ),
            outbound_adapter=OverlayOutboundAdapter(agent),
        )

    def handle_message_body(self, body: Any) -> OverlayHttpResponse:
        if not isinstance(body, dict):
            return OverlayHttpResponse(
                status_code=400,
                body={
                    "mode": "invalid",
                    "state": "FAILED",
                    "reason_code": FailReason.POLICY_REJECTED.value,
                    "detail": "Expected JSON object request body",
                    "response_message": None,
                },
            )
        try:
            result = self.inbound_adapter.handle_request(body)
        except OverlayAdapterError as exc:
            return OverlayHttpResponse(
                status_code=400,
                body={
                    "mode": "invalid",
                    "state": "FAILED",
                    "reason_code": FailReason.POLICY_REJECTED.value,
                    "detail": str(exc),
                    "response_message": None,
                },
            )
        return OverlayHttpResponse(status_code=200, body=result)

    def well_known_document(self) -> dict[str, Any]:
        return self.agent.build_well_known_document(base_url=self.base_url)

    def identity_document_payload(self) -> dict[str, Any]:
        return {"identity_document": self.agent.identity_document}

    @staticmethod
    def well_known_headers() -> dict[str, str]:
        return {"Cache-Control": WELL_KNOWN_CACHE_CONTROL}

    def send_business_payload(
        self,
        *,
        payload: dict[str, Any],
        target_base_url: str | None = None,
        recipient_agent_id: str | None = None,
        context: str | None = None,
        delivery_mode: str = "auto",
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        target, send_result = self.outbound_adapter.send_business_payload(
            payload=payload,
            target_base_url=target_base_url,
            recipient_agent_id=recipient_agent_id,
            context=context,
            delivery_mode=delivery_mode,
            expires_in_seconds=expires_in_seconds,
        )
        return {
            "target": (
                {
                    "agent_id": target.agent_id,
                    "base_url": target.base_url,
                    "well_known_url": target.well_known_url,
                    "identity_document_url": target.identity_document_url,
                }
                if target is not None
                else None
            ),
            "send_result": send_result.to_dict(),
        }

    def send_acp(
        self,
        target_url: str,
        payload: dict[str, Any],
        *,
        recipient_agent_id: str | None = None,
        context: str | None = None,
        delivery_mode: str = "auto",
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        return self.send_business_payload(
            payload=payload,
            target_base_url=target_url,
            recipient_agent_id=recipient_agent_id,
            context=context,
            delivery_mode=delivery_mode,
            expires_in_seconds=expires_in_seconds,
        )


@dataclass
class OverlayClient:
    agent: Agent
    outbound_adapter: OverlayOutboundAdapter

    @classmethod
    def create(cls, *, agent: Agent) -> "OverlayClient":
        return cls(agent=agent, outbound_adapter=OverlayOutboundAdapter(agent))

    def send_acp(
        self,
        target_url: str,
        payload: dict[str, Any],
        *,
        recipient_agent_id: str | None = None,
        context: str | None = None,
        delivery_mode: str = "auto",
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        target, send_result = self.outbound_adapter.send_business_payload(
            payload=payload,
            target_base_url=target_url,
            recipient_agent_id=recipient_agent_id,
            context=context,
            delivery_mode=delivery_mode,
            expires_in_seconds=expires_in_seconds,
        )
        return {
            "target": (
                {
                    "agent_id": target.agent_id,
                    "base_url": target.base_url,
                    "well_known_url": target.well_known_url,
                    "identity_document_url": target.identity_document_url,
                }
                if target is not None
                else None
            ),
            "send_result": send_result.to_dict(),
        }


def _agent_from_overlay_config(config: Any) -> Agent:
    if isinstance(config, Agent):
        return config
    if isinstance(config, OverlayFrameworkRuntime):
        return config.agent
    if isinstance(config, dict):
        candidate = config.get("agent")
        if isinstance(candidate, Agent):
            return candidate
    raise OverlayFrameworkError("acp_overlay_inbound requires config to provide an Agent")


def acp_overlay_inbound(
    config: Any,
    *,
    passthrough: bool = True,
) -> Callable[[InboundDecoratorHandler], Callable[[dict[str, Any]], dict[str, Any]]]:
    agent = _agent_from_overlay_config(config)

    def decorator(handler: InboundDecoratorHandler) -> Callable[[dict[str, Any]], dict[str, Any]]:
        if not callable(handler):
            raise OverlayFrameworkError("acp_overlay_inbound requires a callable handler")
        passthrough_handler: PassThroughHandler | None = None
        if passthrough:
            passthrough_handler = lambda body: handler(body)
        inbound = OverlayInboundAdapter(
            agent=agent,
            business_handler=handler,
            passthrough_handler=passthrough_handler,
        )

        @wraps(handler)
        def wrapper(payload: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(payload, dict):
                raise OverlayFrameworkError(
                    "acp_overlay_inbound wrapped handlers require a JSON object payload argument",
                )
            return inbound.handle_request(payload)

        return wrapper

    return decorator


def register_fastapi_overlay_routes(
    app: Any,
    *,
    runtime: OverlayFrameworkRuntime,
    message_path: str = "/api/v1/acp/messages",
    well_known_path: str = "/.well-known/acp",
    identity_path: str = "/api/v1/acp/identity",
) -> None:
    try:
        from fastapi import Request
        from fastapi.responses import JSONResponse
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise OverlayFrameworkError("FastAPI is not installed; cannot register FastAPI overlay routes") from exc

    globals()["_FastApiRequest"] = Request

    @app.post(message_path)
    async def _acp_overlay_message(request: _FastApiRequest) -> Any:
        try:
            body = await request.json()
        except Exception:  # pragma: no cover - framework parser behavior
            body = None
        response = runtime.handle_message_body(body)
        return JSONResponse(status_code=response.status_code, content=response.body)

    @app.get(well_known_path)
    async def _acp_overlay_well_known() -> Any:
        return JSONResponse(
            status_code=200,
            content=runtime.well_known_document(),
            headers=runtime.well_known_headers(),
        )

    @app.get(identity_path)
    async def _acp_overlay_identity() -> dict[str, Any]:
        return runtime.identity_document_payload()


def register_flask_overlay_routes(
    app: Any,
    *,
    runtime: OverlayFrameworkRuntime,
    message_path: str = "/api/v1/acp/messages",
    well_known_path: str = "/.well-known/acp",
    identity_path: str = "/api/v1/acp/identity",
) -> None:
    try:
        from flask import jsonify, request
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise OverlayFrameworkError("Flask is not installed; cannot register Flask overlay routes") from exc

    def _message() -> Any:
        body = request.get_json(silent=True)
        response = runtime.handle_message_body(body)
        return jsonify(response.body), response.status_code

    def _well_known() -> Any:
        response = jsonify(runtime.well_known_document())
        response.headers["Cache-Control"] = runtime.well_known_headers()["Cache-Control"]
        return response

    def _identity() -> Any:
        return jsonify(runtime.identity_document_payload())

    app.add_url_rule(message_path, endpoint="acp_overlay_message", view_func=_message, methods=["POST"])
    app.add_url_rule(well_known_path, endpoint="acp_overlay_well_known", view_func=_well_known, methods=["GET"])
    app.add_url_rule(identity_path, endpoint="acp_overlay_identity", view_func=_identity, methods=["GET"])
