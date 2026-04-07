# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_TRANSPORT_PROTOCOLS = {"http", "mqtt", "amqp", "relay"}
SUPPORTED_AUTH_TYPES = {"none", "bearer", "basic", "mtls", "username_password", "custom"}


class TransportAuthError(ValueError):
    pass


@dataclass
class AuthConfig:
    type: str = "none"
    parameters: dict[str, str] = field(default_factory=dict)

    def normalized_type(self) -> str:
        normalized = self.type.strip().lower()
        if normalized not in SUPPORTED_AUTH_TYPES:
            raise TransportAuthError(f"Unsupported auth type: {self.type}")
        return normalized

    def normalized_parameters(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in self.parameters.items():
            if value is None:
                continue
            out[str(key)] = str(value)
        return out


@dataclass
class TransportConfig:
    protocol: str
    endpoint: str
    auth: AuthConfig | None = None

    def normalized_protocol(self) -> str:
        normalized = self.protocol.strip().lower()
        if normalized not in SUPPORTED_TRANSPORT_PROTOCOLS:
            raise TransportAuthError(f"Unsupported transport protocol: {self.protocol}")
        return normalized


def auth_config_from_value(value: Any) -> AuthConfig | None:
    if value is None:
        return None
    if isinstance(value, AuthConfig):
        return value
    if not isinstance(value, dict):
        raise TransportAuthError("Transport auth must be an object with fields: type, parameters")
    auth_type = str(value.get("type", "none"))
    parameters_raw = value.get("parameters", {})
    if parameters_raw is None:
        parameters_raw = {}
    if not isinstance(parameters_raw, dict):
        raise TransportAuthError("Transport auth.parameters must be an object")
    parameters: dict[str, str] = {}
    for key, item in parameters_raw.items():
        if item is None:
            continue
        parameters[str(key)] = str(item)
    return AuthConfig(type=auth_type, parameters=parameters)


def transport_config_from_value(value: Any) -> TransportConfig:
    if isinstance(value, TransportConfig):
        return value
    if not isinstance(value, dict):
        raise TransportAuthError("Transport config must be an object")
    protocol = value.get("protocol")
    endpoint = value.get("endpoint")
    if not isinstance(protocol, str) or not protocol.strip():
        raise TransportAuthError("Transport config.protocol must be a non-empty string")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise TransportAuthError("Transport config.endpoint must be a non-empty string")
    auth = auth_config_from_value(value.get("auth"))
    return TransportConfig(protocol=protocol, endpoint=endpoint, auth=auth)
