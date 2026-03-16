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
        allow_insecure_http: bool = False,
        allow_insecure_tls: bool = False,
        ca_file: str | None = None,
        mtls_enabled: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
    ) -> None:
        self.relay_url = relay_url.rstrip("/")
        self.transport = transport or HTTPTransport(
            timeout_seconds=10,
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=cert_file,
            key_file=key_file,
        )

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

    def register_identity_document(self, identity_document: dict[str, Any]) -> dict[str, Any]:
        response = self.transport.post_json(
            f"{self.relay_url}/identities",
            {"identity_document": identity_document},
        )
        if response.status_code != 200:
            detail = response.text.strip()
            raise TransportError(
                f"Relay returned HTTP {response.status_code} while registering identity: {detail}",
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise TransportError("Relay returned a non-JSON registration response") from exc
        if not isinstance(body, dict):
            raise TransportError("Relay registration response must be a JSON object")
        return body

    def discover_identity(self, agent_id: str) -> dict[str, Any]:
        body = self.transport.get_json(
            f"{self.relay_url}/discover",
            params={"agent_id": agent_id},
        )
        identity_document = body.get("identity_document") if isinstance(body, dict) else None
        if identity_document is None and isinstance(body, dict) and "agent_id" in body:
            identity_document = body
        if not isinstance(identity_document, dict):
            raise TransportError(
                f"Relay discovery response did not contain identity_document for {agent_id}",
            )
        return identity_document

    def health(self) -> dict[str, Any]:
        return self._require_object(self.transport.get_json(f"{self.relay_url}/health"), "health response")

    def status(self) -> dict[str, Any]:
        return self._require_object(self.transport.get_json(f"{self.relay_url}/status"), "status response")

    def registry_list(self, *, limit: int = 100) -> dict[str, Any]:
        return self._require_object(
            self.transport.get_json(f"{self.relay_url}/registry", params={"limit": str(limit)}),
            "registry list response",
        )

    def registry_show(self, agent_id: str) -> dict[str, Any]:
        return self._require_object(
            self.transport.get_json(f"{self.relay_url}/registry/{agent_id}"),
            "registry show response",
        )

    def routes_show(self, *, limit: int = 100) -> dict[str, Any]:
        return self._require_object(
            self.transport.get_json(f"{self.relay_url}/routes", params={"limit": str(limit)}),
            "routes response",
        )

    def ops_stats(self) -> dict[str, Any]:
        return self._require_object(self.transport.get_json(f"{self.relay_url}/ops/stats"), "ops stats response")

    def ops_failures(self, *, limit: int = 100) -> dict[str, Any]:
        return self._require_object(
            self.transport.get_json(f"{self.relay_url}/ops/failures", params={"limit": str(limit)}),
            "ops failures response",
        )

    @staticmethod
    def _require_object(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TransportError(f"Relay {label} must be a JSON object")
        return value
