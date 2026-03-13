from __future__ import annotations

from typing import Any

from .messages import ACPMessage
from .transport import HTTPTransport, TransportError


class RelayClient:
    def __init__(
        self,
        relay_url: str,
        *,
        transport: HTTPTransport | None = None,
    ) -> None:
        self.relay_url = relay_url.rstrip("/")
        self.transport = transport or HTTPTransport(timeout_seconds=10)

    def send_message(self, message: ACPMessage) -> dict[str, Any]:
        response = self.transport.post_json(f"{self.relay_url}/messages", message.to_dict())
        if response.status_code != 200:
            detail = response.text.strip()
            raise TransportError(
                f"Relay returned HTTP {response.status_code} for message {message.envelope.message_id}: {detail}",
            )
        try:
            return response.json()
        except ValueError as exc:
            raise TransportError("Relay returned a non-JSON response") from exc
