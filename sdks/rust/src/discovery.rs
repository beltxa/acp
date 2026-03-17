// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::errors::{AcpError, AcpResult};
use crate::http_security::{HttpSecurityPolicy, build_http_client, validate_http_url};
use crate::identity::{parse_agent_id, verify_identity_document};
use crate::well_known::{
    parse_well_known_document, resolve_identity_document_reference, well_known_url_from_base,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CachedDocument {
    identity_document: Map<String, Value>,
    fetched_at: String,
}

#[derive(Debug, Clone)]
pub struct DiscoveryClient {
    cache_path: Option<PathBuf>,
    default_scheme: String,
    relay_hints: Vec<String>,
    enterprise_directory_hints: Vec<String>,
    timeout_seconds: u64,
    policy: HttpSecurityPolicy,
    cache: HashMap<String, CachedDocument>,
    registry: HashMap<String, Map<String, Value>>,
    client: reqwest::blocking::Client,
}

impl DiscoveryClient {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        cache_path: Option<PathBuf>,
        default_scheme: Option<String>,
        relay_hints: Option<Vec<String>>,
        enterprise_directory_hints: Option<Vec<String>>,
        timeout_seconds: u64,
        allow_insecure_http: bool,
        allow_insecure_tls: bool,
        ca_file: Option<String>,
        mtls_enabled: bool,
        cert_file: Option<String>,
        key_file: Option<String>,
    ) -> AcpResult<Self> {
        let policy = HttpSecurityPolicy {
            allow_insecure_http,
            allow_insecure_tls,
            mtls_enabled,
            ca_file,
            cert_file,
            key_file,
        };
        let client = build_http_client(timeout_seconds.max(1), &policy)?;
        let mut instance = Self {
            cache_path,
            default_scheme: default_scheme.unwrap_or_else(|| "https".to_string()),
            relay_hints: relay_hints.unwrap_or_default(),
            enterprise_directory_hints: enterprise_directory_hints.unwrap_or_default(),
            timeout_seconds: timeout_seconds.max(1),
            policy,
            cache: HashMap::new(),
            registry: HashMap::new(),
            client,
        };
        instance.load_cache();
        Ok(instance)
    }

    pub fn seed(&mut self, identity_document: Map<String, Value>) -> AcpResult<()> {
        if let Some(agent_id) = identity_document.get("agent_id").and_then(Value::as_str) {
            self.cache.insert(
                agent_id.to_string(),
                CachedDocument {
                    identity_document,
                    fetched_at: chrono::Utc::now().to_rfc3339(),
                },
            );
            self.persist_cache()?;
        }
        Ok(())
    }

    pub fn register_identity_document(
        &mut self,
        identity_document: Map<String, Value>,
    ) -> AcpResult<()> {
        let agent_id = identity_document
            .get("agent_id")
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| {
                AcpError::Validation("Identity document missing agent_id".to_string())
            })?;
        self.registry
            .insert(agent_id.clone(), identity_document.clone());
        self.cache.insert(
            agent_id,
            CachedDocument {
                identity_document,
                fetched_at: chrono::Utc::now().to_rfc3339(),
            },
        );
        self.persist_cache()
    }

    pub fn resolve(&mut self, agent_id: &str) -> AcpResult<Map<String, Value>> {
        if let Some(registry_doc) = self.registry.get(agent_id) {
            return Ok(registry_doc.clone());
        }
        if let Some(cached) = self.try_cache(agent_id)? {
            return Ok(cached);
        }
        if let Some(well_known) = self.try_well_known(agent_id)? {
            self.cache_identity(agent_id, well_known.clone())?;
            return Ok(well_known);
        }
        if let Some(relay_doc) = self.try_hint_lookups(&self.relay_hints, agent_id)? {
            self.cache_identity(agent_id, relay_doc.clone())?;
            return Ok(relay_doc);
        }
        if let Some(enterprise_doc) =
            self.try_hint_lookups(&self.enterprise_directory_hints, agent_id)?
        {
            self.cache_identity(agent_id, enterprise_doc.clone())?;
            return Ok(enterprise_doc);
        }
        Err(AcpError::Discovery(format!(
            "Unable to resolve identity document for {agent_id}"
        )))
    }

    pub fn resolve_well_known(
        &mut self,
        base_url: &str,
        expected_agent_id: Option<&str>,
    ) -> AcpResult<Map<String, Value>> {
        let well_known_url = well_known_url_from_base(base_url)?;
        let resolved = self
            .resolve_well_known_url(&well_known_url, expected_agent_id)?
            .ok_or_else(|| {
                AcpError::Discovery(format!(
                    "Unable to resolve well-known metadata from {well_known_url}"
                ))
            })?;
        let identity_document = resolved
            .get("identity_document")
            .and_then(Value::as_object)
            .cloned()
            .ok_or_else(|| {
                AcpError::Discovery(
                    "Well-known discovery returned invalid identity document".to_string(),
                )
            })?;
        let agent_id = identity_document
            .get("agent_id")
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| {
                AcpError::Discovery(
                    "Well-known discovery returned identity document without agent_id".to_string(),
                )
            })?;
        self.cache_identity(&agent_id, identity_document)?;
        let mut response = resolved;
        response.insert("well_known_url".to_string(), Value::String(well_known_url));
        Ok(response)
    }

    fn try_cache(&mut self, agent_id: &str) -> AcpResult<Option<Map<String, Value>>> {
        let Some(cached) = self.cache.get(agent_id).cloned() else {
            return Ok(None);
        };
        if cache_valid(&cached.identity_document) {
            return Ok(Some(cached.identity_document));
        }
        self.cache.remove(agent_id);
        self.persist_cache()?;
        Ok(None)
    }

    fn try_well_known(&mut self, agent_id: &str) -> AcpResult<Option<Map<String, Value>>> {
        let parts = parse_agent_id(agent_id)?;
        let Some(domain) = parts.domain else {
            return Ok(None);
        };
        let well_known_url = format!("{}://{domain}/.well-known/acp", self.default_scheme);
        let Some(resolved) = self.resolve_well_known_url(&well_known_url, Some(agent_id))? else {
            return Ok(None);
        };
        let identity_document = resolved
            .get("identity_document")
            .and_then(Value::as_object)
            .cloned();
        Ok(identity_document)
    }

    fn try_hint_lookups(
        &self,
        hints: &[String],
        agent_id: &str,
    ) -> AcpResult<Option<Map<String, Value>>> {
        for hint in hints {
            let url = format!("{}/discover", hint.trim_end_matches('/'));
            let body = self.fetch_json(
                &url,
                Some(&[("agent_id", agent_id)]),
                "Discovery hint lookup",
            )?;
            let Some(body) = body else {
                continue;
            };
            if let Some(identity_document) = extract_identity_document(&body)
                && validate_identity_document(&identity_document)
            {
                return Ok(Some(identity_document));
            }
        }
        Ok(None)
    }

    fn resolve_well_known_url(
        &self,
        well_known_url: &str,
        expected_agent_id: Option<&str>,
    ) -> AcpResult<Option<Map<String, Value>>> {
        let body = self.fetch_json(well_known_url, None, "Discovery .well-known lookup")?;
        let Some(body) = body else {
            return Ok(None);
        };
        let well_known = match parse_well_known_document(&Value::Object(body.clone())) {
            Ok(value) => value,
            Err(_) => return Ok(None),
        };
        if let Some(expected) = expected_agent_id
            && well_known.get("agent_id").and_then(Value::as_str) != Some(expected)
        {
            return Ok(None);
        }
        let identity_reference = resolve_identity_document_reference(&well_known, well_known_url)?;
        let identity_body = self.fetch_json(
            &identity_reference,
            None,
            "Discovery identity document lookup",
        )?;
        let Some(identity_body) = identity_body else {
            return Ok(None);
        };
        let Some(identity_document) = extract_identity_document(&identity_body) else {
            return Ok(None);
        };
        if !validate_identity_document(&identity_document) {
            return Ok(None);
        }
        if let Some(expected) = expected_agent_id
            && identity_document.get("agent_id").and_then(Value::as_str) != Some(expected)
        {
            return Ok(None);
        }
        let mut response = Map::new();
        response.insert("well_known".to_string(), Value::Object(well_known));
        response.insert(
            "identity_document".to_string(),
            Value::Object(identity_document),
        );
        Ok(Some(response))
    }

    fn fetch_json(
        &self,
        url: &str,
        query: Option<&[(&str, &str)]>,
        context: &str,
    ) -> AcpResult<Option<Map<String, Value>>> {
        validate_http_url(
            url,
            self.policy.allow_insecure_http,
            self.policy.mtls_enabled,
            context,
        )?;
        let mut request = self
            .client
            .get(url)
            .timeout(Duration::from_secs(self.timeout_seconds));
        if let Some(query) = query {
            request = request.query(query);
        }
        let response = match request.send() {
            Ok(response) => response,
            Err(_) => return Ok(None),
        };
        if response.status().as_u16() != 200 {
            return Ok(None);
        }
        let value: Value = match response.json() {
            Ok(value) => value,
            Err(_) => return Ok(None),
        };
        Ok(value.as_object().cloned())
    }

    fn cache_identity(
        &mut self,
        agent_id: &str,
        identity_document: Map<String, Value>,
    ) -> AcpResult<()> {
        self.cache.insert(
            agent_id.to_string(),
            CachedDocument {
                identity_document,
                fetched_at: chrono::Utc::now().to_rfc3339(),
            },
        );
        self.persist_cache()
    }

    fn load_cache(&mut self) {
        let Some(path) = &self.cache_path else {
            return;
        };
        let Ok(raw) = fs::read_to_string(path) else {
            return;
        };
        if let Ok(value) = serde_json::from_str::<HashMap<String, CachedDocument>>(&raw) {
            self.cache = value;
        }
    }

    fn persist_cache(&self) -> AcpResult<()> {
        let Some(path) = &self.cache_path else {
            return Ok(());
        };
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let value = serde_json::to_string(&self.cache)?;
        fs::write(path, value)?;
        Ok(())
    }
}

fn cache_valid(identity_document: &Map<String, Value>) -> bool {
    let Some(valid_until) = identity_document.get("valid_until").and_then(Value::as_str) else {
        return false;
    };
    chrono::DateTime::parse_from_rfc3339(valid_until)
        .map(|ts| ts > chrono::Utc::now())
        .unwrap_or(false)
}

fn validate_identity_document(identity_document: &Map<String, Value>) -> bool {
    verify_identity_document(identity_document) && cache_valid(identity_document)
}

fn extract_identity_document(body: &Map<String, Value>) -> Option<Map<String, Value>> {
    if let Some(identity) = body.get("identity_document").and_then(Value::as_object) {
        return Some(identity.clone());
    }
    if body.get("agent_id").is_some() {
        return Some(body.clone());
    }
    None
}
