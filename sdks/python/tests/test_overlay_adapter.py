from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from acp.agent import Agent
from acp.messages import MessageClass
from acp.overlay import OverlayAdapterError, OverlayInboundAdapter, OverlayOutboundAdapter, is_acp_http_message


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


def test_inbound_overlay_processes_acp_message(tmp_path: Path) -> None:
    sender = _make_agent(tmp_path / "sender", "agent:sender@localhost:9950", "http://localhost:9950/api/v1/acp/messages")
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9951", "http://localhost:9951/api/v1/acp/messages")

    received_payloads: list[dict[str, Any]] = []
    inbound = OverlayInboundAdapter(
        receiver,
        business_handler=lambda payload: received_payloads.append(dict(payload)) or {"accepted": True},
    )

    raw_message = sender._build_message(  # noqa: SLF001 - intentional test coverage of runtime path
        recipients=[receiver.agent_id],
        payload={"kind": "overlay-test"},
        recipient_public_keys={
            receiver.agent_id: receiver.identity_document["keys"]["encryption"]["public_key"],
        },
        message_class=MessageClass.SEND,
        context_id="overlay:inbound",
        operation_id="op-inbound",
        expires_in_seconds=120,
        correlation_id=None,
        in_reply_to=None,
    ).to_dict()

    assert is_acp_http_message(raw_message)
    response = inbound.handle_request(raw_message)
    assert response["mode"] == "acp"
    assert response["acp_result"]["state"] == "ACKNOWLEDGED"
    assert isinstance(response["response_message"], dict)
    assert received_payloads == [{"kind": "overlay-test"}]


def test_inbound_overlay_supports_passthrough(tmp_path: Path) -> None:
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9961", "http://localhost:9961/api/v1/acp/messages")
    inbound = OverlayInboundAdapter(
        receiver,
        business_handler=lambda payload: {"ignored": payload},
        passthrough_handler=lambda body: {"echo": body},
    )
    response = inbound.handle_request({"legacy": "payload"})
    assert response == {"mode": "passthrough", "payload": {"echo": {"legacy": "payload"}}}


def test_inbound_overlay_rejects_non_acp_without_passthrough(tmp_path: Path) -> None:
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9962", "http://localhost:9962/api/v1/acp/messages")
    inbound = OverlayInboundAdapter(receiver, business_handler=lambda payload: payload)
    with pytest.raises(OverlayAdapterError):
        inbound.handle_request({"legacy": "payload"})


def test_outbound_overlay_bootstraps_from_well_known(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _make_agent(tmp_path / "sender", "agent:sender@localhost:9970", "http://localhost:9970/api/v1/acp/messages")
    receiver = _make_agent(tmp_path / "receiver", "agent:receiver@localhost:9971", "http://localhost:9971/api/v1/acp/messages")

    receiver_identity = receiver.identity_document
    receiver_endpoint = receiver_identity["service"]["direct_endpoint"]
    well_known = {
        "agent_id": receiver.agent_id,
        "identity_document": "https://receiver.local/api/v1/acp/identity",
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
        if url == "https://receiver.local/.well-known/acp":
            return DummyResponse(200, well_known)
        if url == "https://receiver.local/api/v1/acp/identity":
            return DummyResponse(200, {"identity_document": receiver_identity})
        return DummyResponse(404)

    captured: dict[str, Any] = {}

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

    def fake_post_json(url: str, body: dict[str, Any], **kwargs: Any) -> FakeSendResponse:
        assert kwargs.get("auth") is None
        captured["url"] = url
        captured["body"] = body
        return FakeSendResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(sender.relay_client.transport, "post_json", fake_post_json)

    outbound = OverlayOutboundAdapter(sender)
    target, send_result = outbound.send_business_payload(
        payload={"kind": "outbound-overlay"},
        target_base_url="https://receiver.local",
        context="overlay:outbound",
    )

    assert target is not None
    assert target.agent_id == receiver.agent_id
    assert captured["url"] == receiver_endpoint
    assert send_result.outcomes[0].state.value == "ACKNOWLEDGED"


def test_outbound_overlay_respects_https_first_policy(tmp_path: Path) -> None:
    sender = Agent.load_or_create(
        "agent:sender@localhost:9980",
        storage_dir=tmp_path / "sender",
        endpoint="https://localhost:9980/api/v1/acp/messages",
        discovery_scheme="https",
        allow_insecure_http=False,
    )
    outbound = OverlayOutboundAdapter(sender)
    with pytest.raises(Exception):
        outbound.send_business_payload(
            payload={"kind": "outbound-overlay"},
            target_base_url="http://receiver.local",
            context="overlay:policy",
        )
