from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from acp.agent import Agent
from acp.messages import MessageClass
from acp.overlay_framework import (
    OverlayFrameworkRuntime,
    register_fastapi_overlay_routes,
    register_flask_overlay_routes,
)


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict[str, Any]:
        return self._body


def _make_agent(storage_dir: Path, agent_id: str, endpoint: str) -> Agent:
    return Agent.load_or_create(
        agent_id,
        storage_dir=storage_dir,
        endpoint=endpoint,
        discovery_scheme="http",
        allow_insecure_http=True,
    )


def test_runtime_handles_inbound_message_and_invalid_payload(tmp_path: Path) -> None:
    sender = _make_agent(tmp_path / "sender", "agent:sender@localhost:9050", "http://localhost:9050/api/v1/acp/messages")
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9051", "http://localhost:9051/api/v1/acp/messages")
    runtime = OverlayFrameworkRuntime.create(
        agent=receiver,
        base_url="http://localhost:9051",
        business_handler=lambda payload: {"accepted": True, "echo": payload},
    )

    raw_message = sender._build_message(  # noqa: SLF001
        recipients=[receiver.agent_id],
        payload={"kind": "framework-inbound"},
        recipient_public_keys={
            receiver.agent_id: receiver.identity_document["keys"]["encryption"]["public_key"],
        },
        message_class=MessageClass.SEND,
        context_id="overlay:framework:inbound",
        operation_id="op-framework-inbound",
        expires_in_seconds=120,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()
    response = runtime.handle_message_body(raw_message)
    assert response.status_code == 200
    assert response.body["mode"] == "acp"
    assert response.body["state"] == "ACKNOWLEDGED"
    assert isinstance(response.body["response_message"], dict)

    invalid = runtime.handle_message_body(["not", "json", "object"])
    assert invalid.status_code == 400
    assert invalid.body["state"] == "FAILED"
    assert invalid.body["reason_code"] == "POLICY_REJECTED"


def test_runtime_outbound_send_bootstraps_well_known(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _make_agent(tmp_path / "sender", "agent:sender@localhost:9060", "http://localhost:9060/api/v1/acp/messages")
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9061", "http://localhost:9061/api/v1/acp/messages")
    runtime = OverlayFrameworkRuntime.create(
        agent=sender,
        base_url="http://localhost:9060",
        business_handler=lambda payload: payload,
    )

    receiver_identity = receiver.identity_document
    receiver_endpoint = receiver_identity["service"]["direct_endpoint"]
    well_known = {
        "agent_id": receiver.agent_id,
        "identity_document": "https://receiver.framework.local/api/v1/acp/identity",
        "transports": {"http": {"endpoint": receiver_endpoint}},
        "version": "1.0",
        "security_profile": "https",
    }

    def fake_get(
        url: str,
        params: dict[str, str] | None = None,
        timeout: int = 5,
        **_kwargs: object,
    ) -> DummyResponse:
        if params is not None:
            return DummyResponse(404)
        if url == "https://receiver.framework.local/.well-known/acp":
            return DummyResponse(200, well_known)
        if url == "https://receiver.framework.local/api/v1/acp/identity":
            return DummyResponse(200, {"identity_document": receiver_identity})
        return DummyResponse(404)

    class FakeSendResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "response_message": {
                    "envelope": {
                        "message_class": "ACK",
                    },
                },
            }

    def fake_post_json(url: str, body: dict[str, Any]) -> FakeSendResponse:
        assert url == receiver_endpoint
        assert isinstance(body, dict)
        return FakeSendResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(sender.relay_client.transport, "post_json", fake_post_json)

    result = runtime.send_business_payload(
        payload={"kind": "framework-outbound"},
        target_base_url="https://receiver.framework.local",
        context="overlay:framework:outbound",
    )
    assert result["target"]["agent_id"] == receiver.agent_id
    assert result["send_result"]["outcomes"][0]["state"] == "ACKNOWLEDGED"


def test_register_fastapi_routes_if_available(tmp_path: Path) -> None:
    fastapi = pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError) as exc:
        pytest.skip(f"fastapi test client unavailable: {exc}")

    sender = _make_agent(tmp_path / "sender", "agent:sender@localhost:9070", "http://localhost:9070/api/v1/acp/messages")
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9071", "http://localhost:9071/api/v1/acp/messages")
    runtime = OverlayFrameworkRuntime.create(
        agent=receiver,
        base_url="http://localhost:9071",
        business_handler=lambda payload: {"accepted": True, "echo": payload},
        passthrough_handler=lambda body: {"accepted": True, "echo": body},
    )
    app = fastapi.FastAPI()
    register_fastapi_overlay_routes(app, runtime=runtime)
    client = TestClient(app)

    wk = client.get("/.well-known/acp")
    assert wk.status_code == 200
    assert wk.json()["agent_id"] == receiver.agent_id

    identity = client.get("/api/v1/acp/identity")
    assert identity.status_code == 200
    assert identity.json()["identity_document"]["agent_id"] == receiver.agent_id

    passthrough = client.post("/api/v1/acp/messages", json={"legacy": "payload"})
    assert passthrough.status_code == 200
    assert passthrough.json()["mode"] == "passthrough"

    raw_message = sender._build_message(  # noqa: SLF001
        recipients=[receiver.agent_id],
        payload={"kind": "framework-fastapi"},
        recipient_public_keys={
            receiver.agent_id: receiver.identity_document["keys"]["encryption"]["public_key"],
        },
        message_class=MessageClass.SEND,
        context_id="overlay:framework:fastapi",
        operation_id="op-framework-fastapi",
        expires_in_seconds=120,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()
    acp = client.post("/api/v1/acp/messages", json=raw_message)
    assert acp.status_code == 200
    assert acp.json()["mode"] == "acp"
    assert acp.json()["state"] == "ACKNOWLEDGED"


def test_register_flask_routes_if_available(tmp_path: Path) -> None:
    flask = pytest.importorskip("flask")

    sender = _make_agent(tmp_path / "sender", "agent:sender@localhost:9080", "http://localhost:9080/api/v1/acp/messages")
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9081", "http://localhost:9081/api/v1/acp/messages")
    runtime = OverlayFrameworkRuntime.create(
        agent=receiver,
        base_url="http://localhost:9081",
        business_handler=lambda payload: {"accepted": True, "echo": payload},
        passthrough_handler=lambda body: {"accepted": True, "echo": body},
    )

    app = flask.Flask(__name__)
    register_flask_overlay_routes(app, runtime=runtime)
    client = app.test_client()

    wk = client.get("/.well-known/acp")
    assert wk.status_code == 200
    assert wk.get_json()["agent_id"] == receiver.agent_id

    identity = client.get("/api/v1/acp/identity")
    assert identity.status_code == 200
    assert identity.get_json()["identity_document"]["agent_id"] == receiver.agent_id

    passthrough = client.post("/api/v1/acp/messages", json={"legacy": "payload"})
    assert passthrough.status_code == 200
    assert passthrough.get_json()["mode"] == "passthrough"

    raw_message = sender._build_message(  # noqa: SLF001
        recipients=[receiver.agent_id],
        payload={"kind": "framework-flask"},
        recipient_public_keys={
            receiver.agent_id: receiver.identity_document["keys"]["encryption"]["public_key"],
        },
        message_class=MessageClass.SEND,
        context_id="overlay:framework:flask",
        operation_id="op-framework-flask",
        expires_in_seconds=120,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()
    acp = client.post("/api/v1/acp/messages", json=raw_message)
    assert acp.status_code == 200
    assert acp.get_json()["mode"] == "acp"
    assert acp.get_json()["state"] == "ACKNOWLEDGED"
