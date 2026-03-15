from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class HttpSecurityError(RuntimeError):
    pass


@dataclass(frozen=True)
class HttpSecurityPolicy:
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    ca_file: str | None = None


def to_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def security_state(url: str | None) -> str:
    if not isinstance(url, str) or not url.strip():
        return "missing"
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme == "https":
        return "secure_https"
    if scheme == "http":
        return "insecure_http"
    if not scheme:
        return "missing_scheme"
    return f"non_http:{scheme}"


def enforce_http_security(
    url: str,
    *,
    policy: HttpSecurityPolicy,
    context: str,
) -> list[str]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise HttpSecurityError(
            f"{context} requires an http(s) URL, got: {url}",
        )
    if not parsed.netloc:
        raise HttpSecurityError(f"{context} URL is missing network location: {url}")

    warnings: list[str] = []
    if scheme == "http":
        if not policy.allow_insecure_http:
            raise HttpSecurityError(
                f"{context} uses insecure HTTP ({url}). "
                "Set allow_insecure_http=true only for local/dev/demo workflows.",
            )
        warnings.append(
            f"{context} is using insecure HTTP ({url}) because allow_insecure_http=true",
        )
    if scheme == "https" and policy.allow_insecure_tls:
        warnings.append(
            f"{context} disables TLS certificate verification for {url} "
            "because allow_insecure_tls=true",
        )
    return warnings


def requests_verify_value(url: str, *, policy: HttpSecurityPolicy) -> bool | str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return True
    if policy.allow_insecure_tls:
        return False
    if policy.ca_file:
        return policy.ca_file
    return True
