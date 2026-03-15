from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class HttpSecurityError(RuntimeError):
    pass


@dataclass(frozen=True)
class RelayHttpSecurityPolicy:
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    ca_file: str | None = None
    mtls_enabled: bool = False
    cert_file: str | None = None
    key_file: str | None = None


def enforce_http_security(
    url: str,
    *,
    policy: RelayHttpSecurityPolicy,
    context: str,
) -> list[str]:
    warnings = validate_http_security_policy(policy, context=context)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise HttpSecurityError(f"{context} requires an http(s) URL, got: {url}")
    if not parsed.netloc:
        raise HttpSecurityError(f"{context} URL is missing network location: {url}")

    if scheme == "http":
        if policy.mtls_enabled:
            raise HttpSecurityError(
                f"{context} cannot use HTTP ({url}) when ACP_MTLS_ENABLED=true. Use https:// endpoints.",
            )
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


def requests_cert_value(url: str, *, policy: RelayHttpSecurityPolicy) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return None
    if not policy.mtls_enabled:
        return None
    cert_file = _normalize_file(policy.cert_file)
    key_file = _normalize_file(policy.key_file)
    if cert_file is None or key_file is None:
        raise HttpSecurityError("mTLS requires ACP_CERT_FILE and ACP_KEY_FILE for HTTPS requests")
    return (cert_file, key_file)


def security_profile(policy: RelayHttpSecurityPolicy) -> str:
    labels: list[str] = ["https+mtls" if policy.mtls_enabled else "https"]
    if policy.allow_insecure_http:
        labels.append("insecure-http-override")
    if policy.allow_insecure_tls:
        labels.append("insecure-tls-override")
    return ",".join(labels)


def _normalize_file(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _validate_file(path_value: str | None, *, label: str, context: str) -> str | None:
    normalized = _normalize_file(path_value)
    if normalized is None:
        return None
    if not Path(normalized).is_file():
        raise HttpSecurityError(f"{context} {label} does not exist or is not a file: {normalized}")
    return normalized


def validate_http_security_policy(
    policy: RelayHttpSecurityPolicy,
    *,
    context: str,
    require_client_certificate: bool = True,
) -> list[str]:
    warnings: list[str] = []
    ca_file = _validate_file(policy.ca_file, label="ACP_CA_FILE", context=context)
    cert_file = _validate_file(policy.cert_file, label="ACP_CERT_FILE", context=context)
    key_file = _validate_file(policy.key_file, label="ACP_KEY_FILE", context=context)

    if policy.mtls_enabled:
        if require_client_certificate and cert_file is None:
            raise HttpSecurityError(f"{context} requires ACP_CERT_FILE when ACP_MTLS_ENABLED=true")
        if require_client_certificate and key_file is None:
            raise HttpSecurityError(f"{context} requires ACP_KEY_FILE when ACP_MTLS_ENABLED=true")
        if policy.allow_insecure_tls:
            warnings.append(
                f"{context} has ACP_MTLS_ENABLED=true with ACP_ALLOW_INSECURE_TLS=true. "
                "This is only suitable for local/dev troubleshooting.",
            )
    else:
        if (cert_file is None) != (key_file is None):
            raise HttpSecurityError(
                f"{context} requires both ACP_CERT_FILE and ACP_KEY_FILE when either is configured.",
            )
        if cert_file is not None and key_file is not None:
            warnings.append(
                f"{context} has ACP_CERT_FILE/ACP_KEY_FILE configured while ACP_MTLS_ENABLED=false. "
                "Client certificates are only used for outbound requests when ACP_MTLS_ENABLED=true.",
            )

    if policy.allow_insecure_tls and ca_file is not None:
        warnings.append(
            f"{context} sets ACP_CA_FILE but ACP_ALLOW_INSECURE_TLS=true disables certificate verification.",
        )
    return warnings
