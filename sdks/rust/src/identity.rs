// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::fs;
use std::path::{Path, PathBuf};

use chrono::{Duration, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use uuid::Uuid;

use crate::constants::{ACP_IDENTITY_VERSION, is_supported_trust_profile};
use crate::crypto;
use crate::errors::{AcpError, AcpResult};
use crate::json_support;

const IDENTITY_FILE_NAME: &str = "identity.json";
const IDENTITY_DOC_FILE_NAME: &str = "identity_document.json";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentIdentity {
    #[serde(rename = "agent_id")]
    pub agent_id: String,
    #[serde(rename = "signing_private_key")]
    pub signing_private_key: String,
    #[serde(rename = "signing_public_key")]
    pub signing_public_key: String,
    #[serde(rename = "encryption_private_key")]
    pub encryption_private_key: String,
    #[serde(rename = "encryption_public_key")]
    pub encryption_public_key: String,
    #[serde(rename = "signing_kid")]
    pub signing_kid: String,
    #[serde(rename = "encryption_kid")]
    pub encryption_kid: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentIdParts {
    pub name: String,
    pub domain: Option<String>,
}

#[derive(Debug, Clone)]
pub struct IdentityBundle {
    pub identity: AgentIdentity,
    pub identity_document: Map<String, Value>,
}

impl AgentIdentity {
    pub fn create(agent_id: &str) -> AcpResult<Self> {
        parse_agent_id(agent_id)?;
        let (signing_private_key, signing_public_key) = crypto::generate_ed25519_keypair();
        let (encryption_private_key, encryption_public_key) = crypto::generate_x25519_keypair();
        Ok(Self {
            agent_id: agent_id.to_string(),
            signing_private_key,
            signing_public_key,
            encryption_private_key,
            encryption_public_key,
            signing_kid: format!(
                "sig-{}",
                Uuid::new_v4()
                    .simple()
                    .to_string()
                    .chars()
                    .take(12)
                    .collect::<String>()
            ),
            encryption_kid: format!(
                "enc-{}",
                Uuid::new_v4()
                    .simple()
                    .to_string()
                    .chars()
                    .take(12)
                    .collect::<String>()
            ),
        })
    }

    #[allow(clippy::too_many_arguments)]
    pub fn build_identity_document(
        &self,
        direct_endpoint: Option<&str>,
        relay_hints: &[String],
        trust_profile: &str,
        capabilities: Option<&Map<String, Value>>,
        valid_days: i64,
        amqp_service: Option<&Map<String, Value>>,
        mqtt_service: Option<&Map<String, Value>>,
        http_security_profile: Option<&str>,
        relay_security_profile: Option<&str>,
    ) -> AcpResult<Map<String, Value>> {
        if !is_supported_trust_profile(trust_profile) {
            return Err(AcpError::Validation(format!(
                "Unsupported trust profile: {trust_profile}"
            )));
        }

        let mut service = Map::new();
        if let Some(endpoint) = direct_endpoint {
            service.insert(
                "direct_endpoint".to_string(),
                Value::String(endpoint.to_string()),
            );
        } else {
            service.insert("direct_endpoint".to_string(), Value::Null);
        }
        service.insert(
            "relay_hints".to_string(),
            Value::Array(
                relay_hints
                    .iter()
                    .map(|h| Value::String(h.clone()))
                    .collect(),
            ),
        );
        if let Some(amqp) = amqp_service {
            service.insert("amqp".to_string(), Value::Object(amqp.clone()));
        }
        if let Some(mqtt) = mqtt_service {
            service.insert("mqtt".to_string(), Value::Object(mqtt.clone()));
        }
        if let (Some(endpoint), Some(profile)) = (direct_endpoint, http_security_profile) {
            service.insert(
                "http".to_string(),
                json!({
                    "endpoint": endpoint,
                    "security_profile": profile,
                }),
            );
        }
        if let (Some(profile), Some(first_relay)) = (relay_security_profile, relay_hints.first()) {
            service.insert(
                "relay".to_string(),
                json!({
                    "endpoint": first_relay,
                    "security_profile": profile,
                }),
            );
        }

        let mut document = Map::new();
        document.insert(
            "acp_identity_version".to_string(),
            Value::String(ACP_IDENTITY_VERSION.to_string()),
        );
        document.insert("agent_id".to_string(), Value::String(self.agent_id.clone()));
        document.insert(
            "created_at".to_string(),
            Value::String(Utc::now().to_rfc3339()),
        );
        document.insert(
            "valid_until".to_string(),
            Value::String((Utc::now() + Duration::days(valid_days.max(1))).to_rfc3339()),
        );
        document.insert(
            "trust_profile".to_string(),
            Value::String(trust_profile.to_string()),
        );
        document.insert(
            "keys".to_string(),
            json!({
                "signing": {
                    "kid": self.signing_kid,
                    "alg": "Ed25519",
                    "public_key": self.signing_public_key
                },
                "encryption": {
                    "kid": self.encryption_kid,
                    "alg": "X25519",
                    "public_key": self.encryption_public_key
                }
            }),
        );
        document.insert("service".to_string(), Value::Object(service));
        document.insert(
            "capabilities".to_string(),
            Value::Object(capabilities.cloned().unwrap_or_default()),
        );

        let unsigned = Value::Object(document.clone());
        let signature = crypto::sign_bytes(
            &json_support::canonical_json_bytes(&unsigned)?,
            &self.signing_private_key,
        )?;
        document.insert(
            "signature".to_string(),
            json!({
                "algorithm": "Ed25519",
                "signed_by": self.signing_kid,
                "value": signature,
            }),
        );
        Ok(document)
    }
}

pub fn verify_identity_document(identity_document: &Map<String, Value>) -> bool {
    for required in ["agent_id", "keys", "service", "signature", "valid_until"] {
        if !identity_document.contains_key(required) {
            return false;
        }
    }
    let Some(profile) = as_string(identity_document.get("trust_profile")) else {
        return false;
    };
    if !is_supported_trust_profile(profile) {
        return false;
    }
    let Some(valid_until) = as_string(identity_document.get("valid_until")) else {
        return false;
    };
    let Ok(valid_until) = chrono::DateTime::parse_from_rfc3339(valid_until) else {
        return false;
    };
    if valid_until <= Utc::now() {
        return false;
    }

    let signature_value = identity_document
        .get("signature")
        .and_then(Value::as_object)
        .and_then(|signature| signature.get("value"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let signing_public = identity_document
        .get("keys")
        .and_then(Value::as_object)
        .and_then(|keys| keys.get("signing"))
        .and_then(Value::as_object)
        .and_then(|signing| signing.get("public_key"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let (Some(signature_value), Some(signing_public)) = (signature_value, signing_public) else {
        return false;
    };

    let mut unsigned = identity_document.clone();
    unsigned.remove("signature");
    let Ok(bytes) = json_support::canonical_json_bytes(&Value::Object(unsigned)) else {
        return false;
    };
    crypto::verify_signature(&bytes, signature_value, signing_public)
}

pub fn parse_agent_id(agent_id: &str) -> AcpResult<AgentIdParts> {
    let regex = Regex::new(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
        .map_err(|e| AcpError::Validation(format!("Invalid agent ID regex: {e}")))?;
    let captures = regex
        .captures(agent_id)
        .ok_or_else(|| AcpError::Validation(format!("Invalid agent identifier: {agent_id}")))?;
    let name = captures
        .name("name")
        .map(|m| m.as_str().to_string())
        .ok_or_else(|| AcpError::Validation("agent id missing name".to_string()))?;
    let domain = captures.name("domain").map(|m| m.as_str().to_string());
    Ok(AgentIdParts { name, domain })
}

pub fn sanitize_agent_id(agent_id: &str) -> String {
    agent_id
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

pub fn identity_path(storage_dir: &Path, agent_id: &str) -> PathBuf {
    storage_dir.join(sanitize_agent_id(agent_id))
}

pub fn write_identity(
    storage_dir: &Path,
    identity: &AgentIdentity,
    identity_document: &Map<String, Value>,
) -> AcpResult<()> {
    let path = identity_path(storage_dir, &identity.agent_id);
    fs::create_dir_all(&path)?;
    let identity_json = json_support::canonical_json_string(&serde_json::to_value(identity)?)?;
    let doc_json = json_support::canonical_json_string(&Value::Object(identity_document.clone()))?;
    fs::write(path.join(IDENTITY_FILE_NAME), identity_json)?;
    fs::write(path.join(IDENTITY_DOC_FILE_NAME), doc_json)?;
    Ok(())
}

pub fn read_identity(storage_dir: &Path, agent_id: &str) -> AcpResult<Option<IdentityBundle>> {
    let path = identity_path(storage_dir, agent_id);
    let identity_path = path.join(IDENTITY_FILE_NAME);
    let doc_path = path.join(IDENTITY_DOC_FILE_NAME);
    if !identity_path.exists() || !doc_path.exists() {
        return Ok(None);
    }
    let identity = json_support::from_json::<AgentIdentity>(&fs::read_to_string(identity_path)?)?;
    let identity_document = json_support::map_from_json(&fs::read_to_string(doc_path)?)?;
    Ok(Some(IdentityBundle {
        identity,
        identity_document,
    }))
}

fn as_string(value: Option<&Value>) -> Option<&str> {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
}
