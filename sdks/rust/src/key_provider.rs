// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::errors::{AcpError, AcpResult};
use crate::http_security::{HttpSecurityPolicy, build_http_client, validate_http_url};
use crate::identity::{read_identity, sanitize_agent_id};

pub type KeyProviderInfo = Map<String, Value>;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IdentityKeyMaterial {
    pub signing_private_key: String,
    pub encryption_private_key: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signing_public_key: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub encryption_public_key: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signing_kid: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub encryption_kid: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TlsMaterial {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cert_file: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub key_file: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ca_file: Option<String>,
}

pub trait KeyProvider: Send + Sync {
    fn load_identity_keys(&self, agent_id: &str) -> AcpResult<IdentityKeyMaterial>;
    fn load_tls_material(&self, agent_id: &str) -> AcpResult<TlsMaterial>;
    fn load_ca_bundle(&self, agent_id: &str) -> AcpResult<Option<String>>;
    fn describe(&self) -> KeyProviderInfo;
}

#[derive(Debug, Clone)]
pub struct LocalKeyProvider {
    storage_dir: std::path::PathBuf,
    cert_file: Option<String>,
    key_file: Option<String>,
    ca_file: Option<String>,
}

impl LocalKeyProvider {
    pub fn new(
        storage_dir: std::path::PathBuf,
        cert_file: Option<String>,
        key_file: Option<String>,
        ca_file: Option<String>,
    ) -> Self {
        Self {
            storage_dir,
            cert_file: normalize_optional(cert_file),
            key_file: normalize_optional(key_file),
            ca_file: normalize_optional(ca_file),
        }
    }
}

impl KeyProvider for LocalKeyProvider {
    fn load_identity_keys(&self, agent_id: &str) -> AcpResult<IdentityKeyMaterial> {
        let bundle = read_identity(&self.storage_dir, agent_id)?.ok_or_else(|| {
            AcpError::KeyProvider(format!("Local identity not found for {agent_id}"))
        })?;
        Ok(IdentityKeyMaterial {
            signing_private_key: bundle.identity.signing_private_key,
            encryption_private_key: bundle.identity.encryption_private_key,
            signing_public_key: Some(bundle.identity.signing_public_key),
            encryption_public_key: Some(bundle.identity.encryption_public_key),
            signing_kid: Some(bundle.identity.signing_kid),
            encryption_kid: Some(bundle.identity.encryption_kid),
        })
    }

    fn load_tls_material(&self, _agent_id: &str) -> AcpResult<TlsMaterial> {
        Ok(TlsMaterial {
            cert_file: self.cert_file.clone(),
            key_file: self.key_file.clone(),
            ca_file: self.ca_file.clone(),
        })
    }

    fn load_ca_bundle(&self, _agent_id: &str) -> AcpResult<Option<String>> {
        Ok(self.ca_file.clone())
    }

    fn describe(&self) -> KeyProviderInfo {
        let mut info = Map::new();
        info.insert("provider".to_string(), Value::String("local".to_string()));
        info.insert(
            "storage_dir".to_string(),
            Value::String(self.storage_dir.to_string_lossy().to_string()),
        );
        info
    }
}

#[derive(Debug, Clone)]
pub struct VaultKeyProvider {
    vault_url: String,
    vault_path: String,
    vault_token_env: String,
    token: Option<String>,
    timeout_seconds: u64,
    http_client: Client,
    cache: Arc<Mutex<HashMap<String, Map<String, Value>>>>,
}

impl VaultKeyProvider {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        vault_url: String,
        vault_path: String,
        vault_token_env: Option<String>,
        token: Option<String>,
        timeout_seconds: u64,
        ca_file: Option<String>,
        allow_insecure_tls: bool,
        allow_insecure_http: bool,
    ) -> AcpResult<Self> {
        let vault_url = trim_and_require(&vault_url, "vault_url")?;
        validate_http_url(
            &vault_url,
            allow_insecure_http,
            false,
            "Vault key provider URL",
        )?;
        let vault_path = trim_and_require(&vault_path, "vault_path")?
            .trim_matches('/')
            .to_string();
        let vault_token_env = vault_token_env
            .as_deref()
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .unwrap_or("VAULT_TOKEN")
            .to_string();
        let policy = HttpSecurityPolicy {
            allow_insecure_http,
            allow_insecure_tls,
            mtls_enabled: false,
            ca_file,
            cert_file: None,
            key_file: None,
        };
        let http_client = build_http_client(timeout_seconds.max(1), &policy)?;
        Ok(Self {
            vault_url: vault_url.trim_end_matches('/').to_string(),
            vault_path,
            vault_token_env,
            token: normalize_optional(token),
            timeout_seconds: timeout_seconds.max(1),
            http_client,
            cache: Arc::new(Mutex::new(HashMap::new())),
        })
    }

    fn load_secret(&self, agent_id: &str) -> AcpResult<Map<String, Value>> {
        let path = self.secret_path(agent_id);
        if let Some(cached) = self.cache.lock().ok().and_then(|c| c.get(&path).cloned()) {
            return Ok(cached);
        }
        let token = self.resolve_token().ok_or_else(|| {
            AcpError::KeyProvider(format!(
                "Vault token is missing. Set token or environment variable {}.",
                self.vault_token_env
            ))
        })?;
        let url = format!("{}/v1/{}", self.vault_url, path.trim_start_matches('/'));
        let response = self
            .http_client
            .get(url)
            .header("Accept", "application/json")
            .header("X-Vault-Token", token)
            .timeout(std::time::Duration::from_secs(self.timeout_seconds))
            .send()?;
        if response.status().as_u16() != 200 {
            return Err(AcpError::KeyProvider(format!(
                "Vault returned HTTP {} for path {}",
                response.status().as_u16(),
                path
            )));
        }
        let payload: Value = response.json()?;
        let secret = extract_secret_data(payload, &path)?;
        if let Ok(mut cache) = self.cache.lock() {
            cache.insert(path, secret.clone());
        }
        Ok(secret)
    }

    fn secret_path(&self, agent_id: &str) -> String {
        if self.vault_path.contains("{agent_id}") {
            return self
                .vault_path
                .replace("{agent_id}", &sanitize_agent_id(agent_id));
        }
        if agent_id.trim().is_empty() {
            return self.vault_path.clone();
        }
        format!("{}/{}", self.vault_path, sanitize_agent_id(agent_id))
    }

    fn resolve_token(&self) -> Option<String> {
        if let Some(token) = &self.token {
            return Some(token.clone());
        }
        std::env::var(&self.vault_token_env)
            .ok()
            .and_then(|v| normalize_optional(Some(v)))
    }
}

impl KeyProvider for VaultKeyProvider {
    fn load_identity_keys(&self, agent_id: &str) -> AcpResult<IdentityKeyMaterial> {
        let secret = self.load_secret(agent_id)?;
        let signing_private_key = secret_value(
            &secret,
            &["signing_key", "identity_signing_key", "signing_private_key"],
        )
        .ok_or_else(|| {
            AcpError::KeyProvider(format!(
                "Vault secret for {agent_id} is missing signing_key"
            ))
        })?;
        let encryption_private_key = secret_value(
            &secret,
            &[
                "encryption_key",
                "identity_encryption_key",
                "encryption_private_key",
            ],
        )
        .ok_or_else(|| {
            AcpError::KeyProvider(format!(
                "Vault secret for {agent_id} is missing encryption_key"
            ))
        })?;
        Ok(IdentityKeyMaterial {
            signing_private_key,
            encryption_private_key,
            signing_public_key: secret_value(&secret, &["signing_public_key"]),
            encryption_public_key: secret_value(&secret, &["encryption_public_key"]),
            signing_kid: secret_value(&secret, &["signing_kid"]),
            encryption_kid: secret_value(&secret, &["encryption_kid"]),
        })
    }

    fn load_tls_material(&self, agent_id: &str) -> AcpResult<TlsMaterial> {
        let secret = self.load_secret(agent_id)?;
        Ok(TlsMaterial {
            cert_file: secret_value(&secret, &["tls_cert_file", "tls_cert", "cert_file"]),
            key_file: secret_value(&secret, &["tls_key_file", "tls_key", "key_file"]),
            ca_file: secret_value(&secret, &["ca_bundle_file", "ca_file", "ca_bundle"]),
        })
    }

    fn load_ca_bundle(&self, agent_id: &str) -> AcpResult<Option<String>> {
        let secret = self.load_secret(agent_id)?;
        Ok(secret_value(
            &secret,
            &["ca_bundle_file", "ca_file", "ca_bundle"],
        ))
    }

    fn describe(&self) -> KeyProviderInfo {
        let mut info = Map::new();
        info.insert("provider".to_string(), Value::String("vault".to_string()));
        info.insert(
            "vault_url".to_string(),
            Value::String(self.vault_url.clone()),
        );
        info.insert(
            "vault_path".to_string(),
            Value::String(self.vault_path.clone()),
        );
        info.insert(
            "vault_token_env".to_string(),
            Value::String(self.vault_token_env.clone()),
        );
        info
    }
}

fn extract_secret_data(payload: Value, path: &str) -> AcpResult<Map<String, Value>> {
    let data = payload
        .get("data")
        .and_then(Value::as_object)
        .cloned()
        .ok_or_else(|| {
            AcpError::KeyProvider(format!(
                "Vault response for path {path} is missing data object"
            ))
        })?;
    if let Some(nested) = data.get("data").and_then(Value::as_object) {
        return Ok(nested.clone());
    }
    Ok(data)
}

fn signable(value: &Value) -> Option<String> {
    value
        .as_str()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_string)
}

fn secret_value(secret: &Map<String, Value>, keys: &[&str]) -> Option<String> {
    for key in keys {
        if let Some(value) = secret.get(*key).and_then(signable) {
            return Some(value);
        }
    }
    None
}

fn trim_and_require(value: &str, label: &str) -> AcpResult<String> {
    let normalized = value.trim();
    if normalized.is_empty() {
        return Err(AcpError::KeyProvider(format!(
            "{label} is required for VaultKeyProvider"
        )));
    }
    Ok(normalized.to_string())
}

fn normalize_optional(value: Option<String>) -> Option<String> {
    value.and_then(|v| {
        let normalized = v.trim().to_string();
        if normalized.is_empty() {
            None
        } else {
            Some(normalized)
        }
    })
}
