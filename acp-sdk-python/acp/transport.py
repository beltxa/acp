from __future__ import annotations

from typing import Any
import time

import requests


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
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_status_codes = retry_status_codes or (408, 425, 429, 500, 502, 503, 504)

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        attempt = 0
        while True:
            try:
                response = requests.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    timeout=self.timeout_seconds,
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
