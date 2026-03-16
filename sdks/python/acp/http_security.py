from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class HttpSecurityError(RuntimeError):
    pass


@dataclass(frozen=True)
class HttpSecurityPolicy:
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    ca_file: str | None = None
    mtls_enabled: bool = False
    cert_file: str | None = None
    key_file: str | None = None


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


def security_profile(policy: HttpSecurityPolicy) -> str:
    labels: list[str] = ["https+mtls" if policy.mtls_enabled else "https"]
    if policy.allow_insecure_http:
        labels.append("insecure-http-override")
    if policy.allow_insecure_tls:
        labels.append("insecure-tls-override")
    return ",".join(labels)


def _normalized_file_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _validate_file_path(path_value: str | None, *, label: str, context: str) -> str | None:
    normalized = _normalized_file_path(path_value)
    if normalized is None:
        return None
    if not Path(normalized).is_file():
        raise HttpSecurityError(f"{context} {label} does not exist or is not a file: {normalized}")
    return normalized


def validate_http_security_policy(
    policy: HttpSecurityPolicy,
    *,
    context: str,
    require_client_certificate: bool = True,
) -> list[str]:
    warnings: list[str] = []
    ca_file = _validate_file_path(policy.ca_file, label="ca_file", context=context)
    cert_file = _validate_file_path(policy.cert_file, label="cert_file", context=context)
    key_file = _validate_file_path(policy.key_file, label="key_file", context=context)

    if policy.mtls_enabled:
        if require_client_certificate and cert_file is None:
            raise HttpSecurityError(f"{context} requires cert_file when mtls_enabled=true")
        if require_client_certificate and key_file is None:
            raise HttpSecurityError(f"{context} requires key_file when mtls_enabled=true")
        if policy.allow_insecure_tls:
            warnings.append(
                f"{context} has mtls_enabled=true with allow_insecure_tls=true. "
                "This is only suitable for local/dev troubleshooting.",
            )
    else:
        if (cert_file is None) != (key_file is None):
            raise HttpSecurityError(
                f"{context} requires both cert_file and key_file when either is configured.",
            )
        if cert_file is not None and key_file is not None:
            warnings.append(
                f"{context} has cert_file/key_file configured while mtls_enabled=false. "
                "Client certificates will only be used when mtls_enabled=true.",
            )

    if policy.allow_insecure_tls and ca_file is not None:
        warnings.append(
            f"{context} sets ca_file but allow_insecure_tls=true disables certificate verification.",
        )
    return warnings


def enforce_http_security(
    url: str,
    *,
    policy: HttpSecurityPolicy,
    context: str,
) -> list[str]:
    warnings = validate_http_security_policy(policy, context=context)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise HttpSecurityError(
            f"{context} requires an http(s) URL, got: {url}",
        )
    if not parsed.netloc:
        raise HttpSecurityError(f"{context} URL is missing network location: {url}")

    if scheme == "http":
        if policy.mtls_enabled:
            raise HttpSecurityError(
                f"{context} cannot use HTTP ({url}) when mtls_enabled=true. Use https:// endpoints.",
            )
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


def requests_cert_value(url: str, *, policy: HttpSecurityPolicy) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return None
    if not policy.mtls_enabled:
        return None
    cert_file = _normalized_file_path(policy.cert_file)
    key_file = _normalized_file_path(policy.key_file)
    if cert_file is None or key_file is None:
        raise HttpSecurityError("mTLS requires cert_file and key_file for HTTPS requests")
    return (cert_file, key_file)
