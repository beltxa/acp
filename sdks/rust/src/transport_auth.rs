// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::errors::{AcpError, AcpResult};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthConfig {
    #[serde(rename = "type")]
    pub auth_type: String,
    #[serde(default)]
    pub parameters: HashMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TransportConfig {
    pub protocol: String,
    pub endpoint: String,
    #[serde(default)]
    pub auth: Option<AuthConfig>,
}

pub fn normalize_auth_type(value: &str) -> AcpResult<String> {
    let normalized = value.trim().to_lowercase();
    let normalized = if normalized.is_empty() {
        "none".to_string()
    } else {
        normalized
    };
    match normalized.as_str() {
        "none" | "bearer" | "basic" | "mtls" | "username_password" | "custom" => Ok(normalized),
        _ => Err(AcpError::Validation(format!(
            "Unsupported auth type: {value}"
        ))),
    }
}

pub fn normalize_auth_config(auth: Option<AuthConfig>) -> AcpResult<Option<AuthConfig>> {
    let Some(mut auth) = auth else {
        return Ok(None);
    };
    auth.auth_type = normalize_auth_type(&auth.auth_type)?;
    auth.parameters = auth
        .parameters
        .into_iter()
        .filter_map(|(key, value)| {
            let key = key.trim().to_string();
            if key.is_empty() {
                return None;
            }
            Some((key, value.trim().to_string()))
        })
        .collect();
    Ok(Some(auth))
}

pub fn auth_config_from_value(value: Option<&Value>) -> AcpResult<Option<AuthConfig>> {
    let Some(value) = value else {
        return Ok(None);
    };
    let Value::Object(map) = value else {
        return Err(AcpError::Validation(
            "transport auth must be an object with fields: type, parameters".to_string(),
        ));
    };
    let auth_type = map
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or("none")
        .to_string();
    let mut parameters = HashMap::new();
    match map.get("parameters") {
        None | Some(Value::Null) => {}
        Some(Value::Object(raw)) => {
            for (key, item) in raw {
                if item.is_null() {
                    continue;
                }
                let value = item
                    .as_str()
                    .map(str::to_string)
                    .unwrap_or_else(|| item.to_string());
                parameters.insert(key.to_string(), value);
            }
        }
        Some(_) => {
            return Err(AcpError::Validation(
                "transport auth.parameters must be an object".to_string(),
            ));
        }
    }
    normalize_auth_config(Some(AuthConfig {
        auth_type,
        parameters,
    }))
}

pub fn serialize_auth_config(auth: Option<&AuthConfig>) -> Option<Value> {
    let auth = auth?;
    let mut params = Map::new();
    for (key, value) in &auth.parameters {
        params.insert(key.clone(), Value::String(value.clone()));
    }
    let mut out = Map::new();
    out.insert("type".to_string(), Value::String(auth.auth_type.clone()));
    out.insert("parameters".to_string(), Value::Object(params));
    Some(Value::Object(out))
}

pub fn auth_parameter(auth: &AuthConfig, key: &str, context: &str) -> AcpResult<String> {
    let value = auth
        .parameters
        .get(key)
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
        .ok_or_else(|| AcpError::Validation(format!("{context} requires auth.parameters.{key}")))?;
    Ok(value)
}

pub fn ensure_allowed_auth_types(
    auth: Option<&AuthConfig>,
    allowed: &[&str],
    context: &str,
) -> AcpResult<()> {
    let Some(auth) = auth else {
        return Ok(());
    };
    if allowed.contains(&auth.auth_type.as_str()) {
        return Ok(());
    }
    Err(AcpError::Validation(format!(
        "{context} does not support auth type: {}",
        auth.auth_type
    )))
}
