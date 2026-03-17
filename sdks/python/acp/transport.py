# Copyright 2026 ACP Project
# Licensed under the Apache License, Version 2.0
# See LICENSE file for details.

from __future__ import annotations

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


class TransportError(RuntimeError):
    pass


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
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_status_codes = retry_status_codes or (408, 425, 429, 500, 502, 503, 504)
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

    def _validate_url(self, url: str, *, context: str) -> tuple[bool | str, tuple[str, str] | None]:
        try:
            warning_messages = enforce_http_security(url, policy=self.policy, context=context)
        except HttpSecurityError as exc:
            raise TransportError(str(exc)) from exc
        for warning_message in warning_messages:
            self._emit_warning(warning_message)
        try:
            cert = requests_cert_value(url, policy=self.policy)
        except HttpSecurityError as exc:
            raise TransportError(str(exc)) from exc
        return requests_verify_value(url, policy=self.policy), cert

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        verify, cert = self._validate_url(url, context=f"HTTP {method.upper()} request")
        attempt = 0
        while True:
            try:
                response = requests.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
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

    def post_json(self, url: str, body: dict[str, Any]) -> requests.Response:
        return self._request_with_retries("POST", url, json_body=body)

    def get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = self._request_with_retries("GET", url, params=params)
        if response.status_code != 200:
            raise TransportError(f"HTTP GET {url} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise TransportError(f"HTTP GET {url} did not return JSON") from exc
