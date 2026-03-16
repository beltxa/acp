use serde_json::{Map, Value};
use url::Url;

use crate::constants::{ACP_VERSION, DEFAULT_IDENTITY_DOCUMENT_PATH};
use crate::errors::{AcpError, AcpResult};
use crate::identity::parse_agent_id;

pub const WELL_KNOWN_PATH: &str = "/.well-known/acp";
pub const SUPPORTED_WELL_KNOWN_VERSION: &str = ACP_VERSION;
pub const SUPPORTED_SECURITY_PROFILES: &[&str] = &["http", "https", "mtls", "https+mtls"];

pub fn well_known_url_from_base(base_url: &str) -> AcpResult<String> {
    let normalized = base_url.trim();
    if normalized.is_empty() {
        return Err(AcpError::Validation("base_url is required".to_string()));
    }
    if normalized.ends_with(WELL_KNOWN_PATH) {
        return Ok(normalized.to_string());
    }
    Ok(format!(
        "{}{}",
        normalized.trim_end_matches('/'),
        WELL_KNOWN_PATH
    ))
}

pub fn identity_document_url_from_base(base_url: &str) -> AcpResult<String> {
    let normalized = base_url.trim();
    if normalized.is_empty() {
        return Err(AcpError::Validation("base_url is required".to_string()));
    }
    Ok(format!(
        "{}{}",
        normalized.trim_end_matches('/'),
        DEFAULT_IDENTITY_DOCUMENT_PATH
    ))
}

pub fn build_well_known_document(
    identity_document: &Map<String, Value>,
    base_url: &str,
    identity_document_url: Option<&str>,
    version: Option<&str>,
) -> AcpResult<Map<String, Value>> {
    let Some(agent_id) = identity_document
        .get("agent_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
    else {
        return Err(AcpError::Validation(
            "identity_document.agent_id is required".to_string(),
        ));
    };

    let service = identity_document
        .get("service")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let capabilities = identity_document
        .get("capabilities")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();

    let mut transports = Map::new();
    if let Some(direct_endpoint) = service
        .get("direct_endpoint")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
    {
        let mut http = Map::new();
        http.insert(
            "endpoint".to_string(),
            Value::String(direct_endpoint.to_string()),
        );
        if let Some(profile) = service
            .get("http")
            .and_then(Value::as_object)
            .and_then(|http| http.get("security_profile"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
        {
            http.insert(
                "security_profile".to_string(),
                Value::String(profile.to_string()),
            );
        }
        transports.insert("http".to_string(), Value::Object(http));
    }
    if let Some(relay_hints) = service.get("relay_hints").and_then(Value::as_array) {
        let endpoints = relay_hints
            .iter()
            .filter_map(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .map(str::to_string)
            .collect::<Vec<_>>();
        if !endpoints.is_empty() {
            let mut relay = Map::new();
            relay.insert("endpoint".to_string(), Value::String(endpoints[0].clone()));
            if let Some(profile) = service
                .get("relay")
                .and_then(Value::as_object)
                .and_then(|relay| relay.get("security_profile"))
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|v| !v.is_empty())
            {
                relay.insert(
                    "security_profile".to_string(),
                    Value::String(profile.to_string()),
                );
            }
            if endpoints.len() > 1 {
                relay.insert(
                    "hints".to_string(),
                    Value::Array(endpoints.into_iter().map(Value::String).collect()),
                );
            }
            transports.insert("relay".to_string(), Value::Object(relay));
        }
    }
    if let Some(amqp) = service.get("amqp").and_then(Value::as_object) {
        transports.insert("amqp".to_string(), Value::Object(amqp.clone()));
    }
    if let Some(mqtt) = service.get("mqtt").and_then(Value::as_object) {
        transports.insert("mqtt".to_string(), Value::Object(mqtt.clone()));
    }

    let version = version.unwrap_or(SUPPORTED_WELL_KNOWN_VERSION);
    if version != SUPPORTED_WELL_KNOWN_VERSION {
        return Err(AcpError::Validation(format!(
            "Unsupported well-known version {version}; expected {SUPPORTED_WELL_KNOWN_VERSION}"
        )));
    }
    let identity_ref = identity_document_url
        .map(str::to_string)
        .unwrap_or(identity_document_url_from_base(base_url)?);
    validate_identity_document_reference(&identity_ref)?;

    let mut doc = Map::new();
    doc.insert("agent_id".to_string(), Value::String(agent_id.to_string()));
    doc.insert("identity_document".to_string(), Value::String(identity_ref));
    doc.insert("transports".to_string(), Value::Object(transports.clone()));
    doc.insert("version".to_string(), Value::String(version.to_string()));
    doc.insert(
        "security_profile".to_string(),
        Value::String(infer_security_profile(&transports)),
    );

    if let Some(supports) = capabilities.get("supports").and_then(Value::as_object) {
        let mut capability_names = supports
            .iter()
            .filter(|(_, enabled)| enabled.as_bool().unwrap_or(false))
            .map(|(key, _)| key.to_string())
            .collect::<Vec<_>>();
        capability_names.sort();
        doc.insert(
            "capabilities".to_string(),
            Value::Array(capability_names.into_iter().map(Value::String).collect()),
        );
    }
    Ok(doc)
}

pub fn parse_well_known_document(value: &Value) -> AcpResult<Map<String, Value>> {
    let map = value.as_object().ok_or_else(|| {
        AcpError::Validation("Well-known response must be a JSON object".to_string())
    })?;
    let agent_id = map
        .get("agent_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or_else(|| AcpError::Validation("Well-known response missing agent_id".to_string()))?;
    parse_agent_id(agent_id)?;

    let transports = map
        .get("transports")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            AcpError::Validation("Well-known response missing transports".to_string())
        })?;
    let version = map
        .get("version")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if version != SUPPORTED_WELL_KNOWN_VERSION {
        return Err(AcpError::Validation(format!(
            "Well-known response version must be {SUPPORTED_WELL_KNOWN_VERSION}"
        )));
    }
    let identity_ref = map
        .get("identity_document")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            AcpError::Validation(
                "Well-known response identity_document must be a URL string".to_string(),
            )
        })?;
    validate_identity_document_reference(identity_ref)?;
    validate_transports(transports)?;
    if let Some(profile) = map.get("security_profile").and_then(Value::as_str)
        && !SUPPORTED_SECURITY_PROFILES.contains(&profile)
    {
        return Err(AcpError::Validation(
            "Well-known response security_profile is invalid".to_string(),
        ));
    }
    Ok(map.clone())
}

pub fn resolve_identity_document_reference(
    well_known: &Map<String, Value>,
    source_url: &str,
) -> AcpResult<String> {
    let reference = well_known
        .get("identity_document")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or_else(|| {
            AcpError::Validation(
                "Well-known response identity_document reference is invalid".to_string(),
            )
        })?;
    validate_identity_document_reference(reference)?;
    if Url::parse(reference).is_ok() {
        return Ok(reference.to_string());
    }
    let source = Url::parse(source_url)?;
    source
        .join(reference)
        .map(|url| url.to_string())
        .map_err(AcpError::from)
}

fn validate_identity_document_reference(reference: &str) -> AcpResult<()> {
    if let Ok(parsed) = Url::parse(reference) {
        if !matches!(parsed.scheme(), "http" | "https") {
            return Err(AcpError::Validation(
                "identity_document URL must use http or https".to_string(),
            ));
        }
        if parsed.host_str().unwrap_or_default().trim().is_empty() {
            return Err(AcpError::Validation(
                "identity_document URL is missing host".to_string(),
            ));
        }
        return Ok(());
    }
    if !reference.starts_with('/') {
        return Err(AcpError::Validation(
            "identity_document URL must be absolute http(s) or root-relative path".to_string(),
        ));
    }
    Ok(())
}

fn validate_transports(transports: &Map<String, Value>) -> AcpResult<()> {
    for (transport_name, hint_value) in transports {
        let hint = hint_value.as_object().ok_or_else(|| {
            AcpError::Validation(format!(
                "Well-known transport hint {transport_name} must be an object"
            ))
        })?;
        if let Some(endpoint_value) = hint.get("endpoint") {
            let endpoint = endpoint_value.as_str().ok_or_else(|| {
                AcpError::Validation(format!(
                    "Well-known transport hint {transport_name}.endpoint must be a string"
                ))
            })?;
            let parsed = Url::parse(endpoint).map_err(|_| {
                AcpError::Validation(format!(
                    "Well-known transport hint {transport_name}.endpoint must be an absolute http(s) URL"
                ))
            })?;
            if !matches!(parsed.scheme(), "http" | "https")
                || parsed.host_str().unwrap_or_default().trim().is_empty()
            {
                return Err(AcpError::Validation(format!(
                    "Well-known transport hint {transport_name}.endpoint must be an absolute http(s) URL"
                )));
            }
        }
        if let Some(profile) = hint.get("security_profile").and_then(Value::as_str)
            && !SUPPORTED_SECURITY_PROFILES.contains(&profile)
        {
            return Err(AcpError::Validation(format!(
                "Well-known transport hint {transport_name}.security_profile is invalid"
            )));
        }
    }
    Ok(())
}

fn infer_security_profile(transports: &Map<String, Value>) -> String {
    for transport in ["http", "relay"] {
        if let Some(profile) = transports
            .get(transport)
            .and_then(Value::as_object)
            .and_then(|hint| hint.get("security_profile"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
        {
            return profile.to_string();
        }
    }
    if let Some(endpoint) = transports
        .get("http")
        .and_then(Value::as_object)
        .and_then(|hint| hint.get("endpoint"))
        .and_then(Value::as_str)
    {
        if endpoint.starts_with("https://") {
            return "https".to_string();
        }
        if endpoint.starts_with("http://") {
            return "http".to_string();
        }
    }
    "https".to_string()
}
