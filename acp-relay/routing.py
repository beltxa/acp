from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import requests


_AGENT_ID_PATTERN = re.compile(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")


def _parse_agent_id(agent_id: str) -> tuple[str, str | None]:
    match = _AGENT_ID_PATTERN.match(agent_id)
    if match is None:
        raise ValueError(f"Invalid agent identifier: {agent_id}")
    return match.group("name"), match.group("domain")


def _is_identity_document(value: dict[str, Any]) -> bool:
    required = ("agent_id", "keys", "service", "valid_until")
    return all(key in value for key in required)


@dataclass
class RelayRoutingConfig:
    default_scheme: str = "https"
    timeout_seconds: int = 5
    relay_hints: list[str] | None = None


class RelayDiscoveryResolver:
    def __init__(self, config: RelayRoutingConfig) -> None:
        self.config = config
        self.cache: dict[str, dict[str, Any]] = {}
        self.registry: dict[str, dict[str, Any]] = {}

    def register_identity_document(self, identity_document: dict[str, Any]) -> None:
        if not _is_identity_document(identity_document):
            raise ValueError("Invalid identity document")
        agent_id = identity_document["agent_id"]
        self.registry[agent_id] = identity_document
        self.cache[agent_id] = identity_document

    def _well_known_url(self, agent_id: str) -> str:
        name, domain = _parse_agent_id(agent_id)
        if not domain:
            raise ValueError(f"Agent id {agent_id} has no domain")
        return f"{self.config.default_scheme}://{domain}/.well-known/acp/agents/{name}"

    def _fetch_well_known(self, agent_id: str) -> dict[str, Any] | None:
        try:
            url = self._well_known_url(agent_id)
        except ValueError:
            return None
        try:
            response = requests.get(url, timeout=self.config.timeout_seconds)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            value = response.json()
        except ValueError:
            return None
        if not isinstance(value, dict) or not _is_identity_document(value):
            return None
        return value

    def _fetch_via_hints(self, agent_id: str) -> dict[str, Any] | None:
        for relay_hint in self.config.relay_hints or []:
            url = f"{relay_hint.rstrip('/')}/discover"
            try:
                response = requests.get(
                    url,
                    params={"agent_id": agent_id},
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException:
                continue
            if response.status_code != 200:
                continue
            try:
                value = response.json()
            except ValueError:
                continue
            if isinstance(value, dict) and "identity_document" in value:
                value = value["identity_document"]
            if not isinstance(value, dict) or not _is_identity_document(value):
                continue
            return value
        return None

    def resolve(self, agent_id: str) -> dict[str, Any]:
        if agent_id in self.registry:
            return self.registry[agent_id]
        if agent_id in self.cache:
            return self.cache[agent_id]

        identity_document = self._fetch_well_known(agent_id)
        if identity_document is None:
            identity_document = self._fetch_via_hints(agent_id)
        if identity_document is None:
            raise LookupError(f"Unable to resolve recipient identity for {agent_id}")

        self.cache[agent_id] = identity_document
        return identity_document


class RelayRouter:
    def __init__(self, resolver: RelayDiscoveryResolver, *, timeout_seconds: int = 10) -> None:
        self.resolver = resolver
        self.timeout_seconds = timeout_seconds

    def route_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        envelope = message.get("envelope", {})
        recipients = envelope.get("recipients", [])
        outcomes: list[dict[str, Any]] = []

        for recipient in recipients:
            outcome: dict[str, Any] = {"recipient": recipient, "state": "FAILED"}
            try:
                identity_document = self.resolver.resolve(recipient)
            except LookupError as exc:
                outcome["detail"] = str(exc)
                outcome["reason_code"] = "POLICY_REJECTED"
                outcomes.append(outcome)
                continue

            endpoint = identity_document.get("service", {}).get("direct_endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                outcome["detail"] = "Recipient identity document missing direct_endpoint"
                outcome["reason_code"] = "POLICY_REJECTED"
                outcomes.append(outcome)
                continue

            try:
                response = requests.post(endpoint, json=message, timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                outcome["detail"] = f"Delivery transport error: {exc}"
                outcome["reason_code"] = "POLICY_REJECTED"
                outcomes.append(outcome)
                continue

            outcome["status_code"] = response.status_code
            body: dict[str, Any] | None = None
            try:
                body = response.json()
            except ValueError:
                body = None

            response_message = body.get("response_message") if isinstance(body, dict) else None
            if response_message is not None:
                outcome["response_message"] = response_message
                response_class = (
                    response_message.get("envelope", {}).get("message_class")
                    if isinstance(response_message, dict)
                    else None
                )
                if isinstance(response_class, str):
                    outcome["response_class"] = response_class

            if isinstance(body, dict):
                reason_code = body.get("reason_code")
                detail = body.get("detail")
                if isinstance(reason_code, str):
                    outcome["reason_code"] = reason_code
                if isinstance(detail, str):
                    outcome["detail"] = detail

            if 200 <= response.status_code < 300:
                response_class = outcome.get("response_class")
                if response_class == "FAIL":
                    outcome["state"] = "FAILED"
                elif response_class in {"ACK", "CAPABILITIES"}:
                    outcome["state"] = "ACKNOWLEDGED"
                else:
                    outcome["state"] = "DELIVERED"
            else:
                outcome["state"] = "FAILED"
                if "detail" not in outcome:
                    outcome["detail"] = f"Recipient HTTP {response.status_code}"

            outcomes.append(outcome)

        return outcomes
