from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


class HttpSecurityError(RuntimeError):
    pass


@dataclass(frozen=True)
class RelayHttpSecurityPolicy:
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    ca_file: str | None = None


def enforce_http_security(
    url: str,
    *,
    policy: RelayHttpSecurityPolicy,
    context: str,
) -> list[str]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise HttpSecurityError(f"{context} requires an http(s) URL, got: {url}")
    if not parsed.netloc:
        raise HttpSecurityError(f"{context} URL is missing network location: {url}")

    warnings: list[str] = []
    if scheme == "http":
        if not policy.allow_insecure_http:
            raise HttpSecurityError(
                f"{context} uses insecure HTTP ({url}). "
                "Set ACP_ALLOW_INSECURE_HTTP=true only for local/dev/demo workflows.",
            )
        warnings.append(
            f"{context} is using insecure HTTP ({url}) because ACP_ALLOW_INSECURE_HTTP=true",
        )
    if scheme == "https" and policy.allow_insecure_tls:
        warnings.append(
            f"{context} disables TLS certificate verification for {url} "
            "because ACP_ALLOW_INSECURE_TLS=true",
        )
    return warnings


def requests_verify_value(url: str, *, policy: RelayHttpSecurityPolicy) -> bool | str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return True
    if policy.allow_insecure_tls:
        return False
    if policy.ca_file:
        return policy.ca_file
    return True
