# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

import base64
from dataclasses import replace
import warnings
from typing import Any
import time

import requests

from .http_security import (
    HttpSecurityError,
    HttpSecurityPolicy,
    enforce_http_security,
    requests_cert_value,
    requests_verify_value,
    validate_http_security_policy,
)
from .transport_auth import AuthConfig, TransportAuthError, auth_config_from_value


class TransportError(RuntimeError):
    pass


_HTTP_AUTH_TYPES = {"none", "bearer", "basic", "mtls", "custom"}


def _normalize_http_auth(value: AuthConfig | dict[str, Any] | None) -> AuthConfig | None:
    try:
        parsed = auth_config_from_value(value)
    except TransportAuthError as exc:
        raise TransportError(str(exc)) from exc
    if parsed is None:
        return None
    auth_type = parsed.normalized_type()
    if auth_type not in _HTTP_AUTH_TYPES:
        raise TransportError(f"Auth type '{auth_type}' is not supported for HTTP/relay transport")
    return AuthConfig(type=auth_type, parameters=parsed.normalized_parameters())


def _require_parameter(parameters: dict[str, str], *, key: str, context: str) -> str:
    value = parameters.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TransportError(f"{context} requires auth.parameters.{key}")
    return value.strip()


def _http_auth_headers(auth: AuthConfig | None) -> dict[str, str]:
    if auth is None:
        return {}
    auth_type = auth.normalized_type()
    params = auth.normalized_parameters()

    if auth_type in {"none", "mtls"}:
        return {}
    if auth_type == "bearer":
        token = _require_parameter(params, key="token", context="Bearer auth")
        return {"Authorization": f"Bearer {token}"}
    if auth_type == "basic":
        username = _require_parameter(params, key="username", context="Basic auth")
        password = _require_parameter(params, key="password", context="Basic auth")
        raw = f"{username}:{password}".encode("utf-8")
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}
    if auth_type == "custom":
        header = params.get("header")
        value = params.get("value")
        scheme = params.get("scheme")
        if isinstance(header, str) and header.strip():
            header_value = _require_parameter(params, key="value", context="Custom auth")
            return {header.strip(): header_value}
        if isinstance(scheme, str) and scheme.strip():
            custom_value = _require_parameter(params, key="value", context="Custom auth")
            return {"Authorization": f"{scheme.strip()} {custom_value}"}
        raise TransportError(
            "Custom auth requires either parameters.header + parameters.value or "
            "parameters.scheme + parameters.value",
        )
    raise TransportError(f"Unsupported HTTP auth type: {auth_type}")


class HTTPTransport:
    def __init__(
        self,
        *,
        timeout_seconds: int = 10,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.2,
        retry_status_codes: tuple[int, ...] | None = None,
        allow_insecure_http: bool = False,
        allow_insecure_tls: bool = False,
        ca_file: str | None = None,
        mtls_enabled: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
        auth: AuthConfig | dict[str, Any] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_status_codes = retry_status_codes or (408, 425, 429, 500, 502, 503, 504)
        self.default_auth = _normalize_http_auth(auth)
        self.policy = HttpSecurityPolicy(
            allow_insecure_http=allow_insecure_http,
            allow_insecure_tls=allow_insecure_tls,
            ca_file=ca_file,
            mtls_enabled=mtls_enabled,
            cert_file=cert_file,
            key_file=key_file,
        )
        self._warned_messages: set[str] = set()
        try:
            warning_messages = validate_http_security_policy(
                self.policy,
                context="HTTP transport configuration",
            )
        except HttpSecurityError as exc:
            raise TransportError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)

    def _emit_warning(self, message: str) -> None:
        if message in self._warned_messages:
            return
        self._warned_messages.add(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _effective_policy_for_auth(self, auth: AuthConfig | None) -> HttpSecurityPolicy:
        if auth is None or auth.normalized_type() != "mtls":
            return self.policy
        params = auth.normalized_parameters()
        cert_path = _require_parameter(params, key="cert_path", context="mTLS auth")
        key_path = _require_parameter(params, key="key_path", context="mTLS auth")
        ca_path = params.get("ca_path")
        return replace(
            self.policy,
            mtls_enabled=True,
            cert_file=cert_path,
            key_file=key_path,
            ca_file=ca_path if isinstance(ca_path, str) and ca_path.strip() else self.policy.ca_file,
        )

    def _validate_url(
        self,
        url: str,
        *,
        context: str,
        policy: HttpSecurityPolicy,
    ) -> tuple[bool | str, tuple[str, str] | None]:
        try:
            warning_messages = enforce_http_security(url, policy=policy, context=context)
        except HttpSecurityError as exc:
            raise TransportError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        try:
            cert = requests_cert_value(url, policy=policy)
        except HttpSecurityError as exc:
            raise TransportError(str(exc)) from exc
        return requests_verify_value(url, policy=policy), cert

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        auth: AuthConfig | dict[str, Any] | None = None,
    ) -> requests.Response:
        active_auth = _normalize_http_auth(auth) if auth is not None else self.default_auth
        policy = self._effective_policy_for_auth(active_auth)
        verify, cert = self._validate_url(
            url,
            context=f"HTTP {method.upper()} request",
            policy=policy,
        )
        headers = _http_auth_headers(active_auth)
        attempt = 0
        while True:
            try:
                response = requests.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers=headers or None,
                    timeout=self.timeout_seconds,
                    verify=verify,
                    cert=cert,
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise TransportError(f"HTTP {method} failed for {url}: {exc}") from exc
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                attempt += 1
                continue

            if response.status_code in self.retry_status_codes and attempt < self.max_retries:
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                attempt += 1
                continue
            return response

    def post_json(
        self,
        url: str,
        body: dict[str, Any],
        *,
        auth: AuthConfig | dict[str, Any] | None = None,
    ) -> requests.Response:
        return self._request_with_retries("POST", url, json_body=body, auth=auth)

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        auth: AuthConfig | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._request_with_retries("GET", url, params=params, auth=auth)
        if response.status_code != 200:
            raise TransportError(f"HTTP GET {url} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise TransportError(f"HTTP GET {url} did not return JSON") from exc
