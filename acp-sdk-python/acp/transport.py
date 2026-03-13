from __future__ import annotations

from typing import Any

import requests


class TransportError(RuntimeError):
    pass


class HTTPTransport:
    def __init__(self, *, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    def post_json(self, url: str, body: dict[str, Any]) -> requests.Response:
        try:
            return requests.post(url, json=body, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise TransportError(f"HTTP POST failed for {url}: {exc}") from exc

    def get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = requests.get(url, params=params, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise TransportError(f"HTTP GET failed for {url}: {exc}") from exc
        if response.status_code != 200:
            raise TransportError(f"HTTP GET {url} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise TransportError(f"HTTP GET {url} did not return JSON") from exc
