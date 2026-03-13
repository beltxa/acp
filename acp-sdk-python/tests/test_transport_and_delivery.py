from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from acp import Agent, DeliveryState
from acp.transport import HTTPTransport, TransportError


class DummyResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body
        self.text = "" if body is None else str(body)

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


def test_http_transport_retries_on_transient_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_request(method: str, url: str, **_: Any) -> DummyResponse:
        calls.append(1)
        if len(calls) < 3:
            raise requests.RequestException("transient failure")
        return DummyResponse(200, {"status": "ok"})

    monkeypatch.setattr(requests, "request", fake_request)
    transport = HTTPTransport(max_retries=2, retry_backoff_seconds=0.0)
    response = transport.post_json("http://localhost:9000/test", {"hello": "world"})

    assert response.status_code == 200
    assert len(calls) == 3


def test_http_transport_raises_after_retry_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(method: str, url: str, **_: Any) -> DummyResponse:
        raise requests.RequestException("still failing")

    monkeypatch.setattr(requests, "request", fake_request)
    transport = HTTPTransport(max_retries=1, retry_backoff_seconds=0.0)

    with pytest.raises(TransportError):
        transport.post_json("http://localhost:9000/test", {"hello": "world"})


def test_send_direct_delivery_mode_uses_recipient_endpoint(tmp_path: Path) -> None:
    sender = Agent.create(
        "agent:sender.bot@localhost:9300",
        storage_dir=tmp_path / "sender",
        endpoint="http://localhost:9300/acp/inbox",
        relay_url="http://localhost:8080",
        relay_hints=["http://localhost:8080"],
        discovery_scheme="http",
    )
    recipient = Agent.create(
        "agent:recipient.bot@localhost:9301",
        storage_dir=tmp_path / "recipient",
        endpoint="http://localhost:9301/acp/inbox",
        relay_url="http://localhost:8080",
        relay_hints=["http://localhost:8080"],
        discovery_scheme="http",
    )

    class InMemoryDirectTransport:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def post_json(self, url: str, body: dict[str, Any]) -> DummyResponse:
            self.urls.append(url)
            if url != "http://localhost:9301/acp/inbox":
                return DummyResponse(404, {"detail": "unknown endpoint"})
            result = recipient.handle_incoming(body)
            return DummyResponse(200, result)

    direct_transport = InMemoryDirectTransport()
    sender.relay_client.transport = direct_transport  # type: ignore[assignment]
    sender.discovery.resolve = (  # type: ignore[method-assign]
        lambda agent_id: recipient.identity_document
        if agent_id == recipient.agent_id
        else sender.identity_document
    )

    result = sender.send(
        recipients=[recipient.agent_id],
        payload={"type": "ping"},
        context="ctx-direct",
        delivery_mode="direct",
    )

    assert direct_transport.urls == ["http://localhost:9301/acp/inbox"]
    assert result.outcomes[0].state is DeliveryState.ACKNOWLEDGED
    assert result.message_ids == [result.message_id]
