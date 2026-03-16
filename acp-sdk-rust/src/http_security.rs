use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use reqwest::Certificate;
use reqwest::Identity;
use reqwest::blocking::Client;
use url::Url;

use crate::errors::{AcpError, AcpResult};

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct HttpSecurityPolicy {
    #[serde(default)]
    pub allow_insecure_http: bool,
    #[serde(default)]
    pub allow_insecure_tls: bool,
    #[serde(default)]
    pub mtls_enabled: bool,
    pub ca_file: Option<String>,
    pub cert_file: Option<String>,
    pub key_file: Option<String>,
}

pub fn validate_http_url(
    url: &str,
    allow_insecure_http: bool,
    mtls_enabled: bool,
    context: &str,
) -> AcpResult<Url> {
    let parsed = Url::parse(url)?;
    match parsed.scheme() {
        "http" | "https" => {}
        _ => {
            return Err(AcpError::Validation(format!(
                "{context} requires an http(s) URL, got: {url}"
            )));
        }
    }
    if parsed.host_str().unwrap_or_default().trim().is_empty() {
        return Err(AcpError::Validation(format!(
            "{context} URL is missing host: {url}"
        )));
    }
    if parsed.scheme() == "http" && mtls_enabled {
        return Err(AcpError::Validation(format!(
            "{context} cannot use HTTP ({url}) when mtls_enabled=true. Use https:// endpoints."
        )));
    }
    if parsed.scheme() == "http" && !allow_insecure_http {
        return Err(AcpError::Validation(format!(
            "{context} uses insecure HTTP ({url}). Set allow_insecure_http=true only for local/dev/demo workflows."
        )));
    }
    Ok(parsed)
}

pub fn validate_http_client_policy(policy: &HttpSecurityPolicy, context: &str) -> AcpResult<()> {
    let _ca = normalize_optional_file(policy.ca_file.as_deref(), context, "ca_file")?;
    let cert = normalize_optional_file(policy.cert_file.as_deref(), context, "cert_file")?;
    let key = normalize_optional_file(policy.key_file.as_deref(), context, "key_file")?;
    if policy.mtls_enabled {
        if cert.is_none() {
            return Err(AcpError::Validation(format!(
                "{context} requires cert_file when mtls_enabled=true"
            )));
        }
        if key.is_none() {
            return Err(AcpError::Validation(format!(
                "{context} requires key_file when mtls_enabled=true"
            )));
        }
    } else if cert.is_some() ^ key.is_some() {
        return Err(AcpError::Validation(format!(
            "{context} requires both cert_file and key_file when either is configured"
        )));
    }
    Ok(())
}

pub fn build_http_client(timeout_seconds: u64, policy: &HttpSecurityPolicy) -> AcpResult<Client> {
    validate_http_client_policy(policy, "HTTP client configuration")?;
    let mut builder = Client::builder()
        .timeout(Duration::from_secs(timeout_seconds.max(1)))
        .connect_timeout(Duration::from_secs(timeout_seconds.max(1)));

    if policy.allow_insecure_tls {
        builder = builder
            .danger_accept_invalid_certs(true)
            .danger_accept_invalid_hostnames(true);
    }

    if let Some(ca_path) = normalize_optional_file(
        policy.ca_file.as_deref(),
        "HTTP client configuration",
        "ca_file",
    )? {
        let bytes = fs::read(ca_path)?;
        let cert = Certificate::from_pem(&bytes)
            .map_err(|e| AcpError::Validation(format!("invalid ca_file PEM: {e}")))?;
        builder = builder.add_root_certificate(cert);
    }

    if policy.mtls_enabled {
        let cert_path = normalize_optional_file(
            policy.cert_file.as_deref(),
            "HTTP client configuration",
            "cert_file",
        )?
        .ok_or_else(|| {
            AcpError::Validation("cert_file is required when mtls_enabled=true".to_string())
        })?;
        let key_path = normalize_optional_file(
            policy.key_file.as_deref(),
            "HTTP client configuration",
            "key_file",
        )?
        .ok_or_else(|| {
            AcpError::Validation("key_file is required when mtls_enabled=true".to_string())
        })?;
        let cert_pem = fs::read(cert_path)?;
        let key_pem = fs::read(key_path)?;
        let mut combined = Vec::with_capacity(cert_pem.len() + key_pem.len() + 2);
        combined.extend_from_slice(&cert_pem);
        if !combined.ends_with(b"\n") {
            combined.push(b'\n');
        }
        combined.extend_from_slice(&key_pem);
        let identity = Identity::from_pem(&combined)
            .map_err(|e| AcpError::Validation(format!("invalid mTLS cert/key PEM: {e}")))?;
        builder = builder.identity(identity);
    }

    builder
        .build()
        .map_err(|e| AcpError::Transport(format!("unable to build HTTP client: {e}")))
}

pub fn normalize_optional_file(
    value: Option<&str>,
    context: &str,
    label: &str,
) -> AcpResult<Option<PathBuf>> {
    let Some(raw) = value.map(str::trim).filter(|v| !v.is_empty()) else {
        return Ok(None);
    };
    let path = Path::new(raw);
    if !path.is_file() {
        return Err(AcpError::Validation(format!(
            "{context} {label} does not exist or is not a file: {raw}"
        )));
    }
    Ok(Some(path.to_path_buf()))
}
