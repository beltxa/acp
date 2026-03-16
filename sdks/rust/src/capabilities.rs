use chrono::{Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::constants::{ACP_VERSION, DEFAULT_CRYPTO_SUITE};
use crate::json_support::JsonMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentCapabilities {
    #[serde(rename = "agent_id")]
    pub agent_id: String,
    #[serde(rename = "protocol_versions")]
    pub protocol_versions: Vec<String>,
    #[serde(rename = "crypto_suites")]
    pub crypto_suites: Vec<String>,
    pub transports: Vec<String>,
    pub supports: JsonMap,
    pub limits: JsonMap,
    pub profiles: Vec<String>,
    #[serde(rename = "valid_until")]
    pub valid_until: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CapabilityMatch {
    pub compatible: bool,
    pub protocol_version: Option<String>,
    pub crypto_suite: Option<String>,
    pub transport: Option<String>,
    pub reason: Option<String>,
}

impl CapabilityMatch {
    pub fn compatible(protocol_version: String, crypto_suite: String, transport: String) -> Self {
        Self {
            compatible: true,
            protocol_version: Some(protocol_version),
            crypto_suite: Some(crypto_suite),
            transport: Some(transport),
            reason: None,
        }
    }

    pub fn incompatible(reason: impl Into<String>) -> Self {
        Self {
            compatible: false,
            protocol_version: None,
            crypto_suite: None,
            transport: None,
            reason: Some(reason.into()),
        }
    }
}

impl AgentCapabilities {
    pub fn new(agent_id: impl Into<String>) -> Self {
        let mut supports = Map::new();
        supports.insert("ack".to_string(), Value::Bool(true));
        supports.insert("fail".to_string(), Value::Bool(true));
        supports.insert("compensate".to_string(), Value::Bool(true));
        supports.insert("direct_delivery".to_string(), Value::Bool(true));
        supports.insert("relay_delivery".to_string(), Value::Bool(true));
        supports.insert("amqp_delivery".to_string(), Value::Bool(true));
        supports.insert("mqtt_delivery".to_string(), Value::Bool(true));

        let mut limits = Map::new();
        limits.insert(
            "max_payload_bytes".to_string(),
            Value::Number(1048576_u64.into()),
        );

        Self {
            agent_id: agent_id.into(),
            protocol_versions: vec![ACP_VERSION.to_string()],
            crypto_suites: vec![DEFAULT_CRYPTO_SUITE.to_string()],
            transports: vec![
                "https".to_string(),
                "http".to_string(),
                "relay".to_string(),
                "amqp".to_string(),
                "mqtt".to_string(),
            ],
            supports,
            limits,
            profiles: vec!["core".to_string(), "self_asserted".to_string()],
            valid_until: (Utc::now() + Duration::days(365)).to_rfc3339(),
        }
    }

    pub fn from_map(value: Option<&JsonMap>, fallback_agent_id: &str) -> Self {
        if let Some(raw) = value {
            if let Ok(mut parsed) = serde_json::from_value::<Self>(Value::Object(raw.clone())) {
                if parsed.agent_id.trim().is_empty() {
                    parsed.agent_id = fallback_agent_id.to_string();
                }
                if parsed.protocol_versions.is_empty() {
                    parsed.protocol_versions = vec![ACP_VERSION.to_string()];
                }
                if parsed.crypto_suites.is_empty() {
                    parsed.crypto_suites = vec![DEFAULT_CRYPTO_SUITE.to_string()];
                }
                if parsed.transports.is_empty() {
                    parsed.transports = vec![
                        "https".to_string(),
                        "http".to_string(),
                        "relay".to_string(),
                        "amqp".to_string(),
                        "mqtt".to_string(),
                    ];
                }
                return parsed;
            }
        }
        Self::new(fallback_agent_id.to_string())
    }

    pub fn to_map(&self) -> JsonMap {
        serde_json::to_value(self)
            .ok()
            .and_then(|v| v.as_object().cloned())
            .unwrap_or_default()
    }

    pub fn choose_compatible(&self, remote: &AgentCapabilities) -> CapabilityMatch {
        let protocol_version =
            first_intersection(&self.protocol_versions, &remote.protocol_versions);
        if protocol_version.is_none() {
            return CapabilityMatch::incompatible("No compatible protocol version");
        }
        let crypto_suite = first_intersection(&self.crypto_suites, &remote.crypto_suites);
        if crypto_suite.is_none() {
            return CapabilityMatch::incompatible("No compatible crypto suite");
        }
        let transport = first_intersection(&self.transports, &remote.transports);
        if transport.is_none() {
            return CapabilityMatch::incompatible("No compatible transport");
        }
        CapabilityMatch::compatible(
            protocol_version.unwrap_or_default(),
            crypto_suite.unwrap_or_default(),
            transport.unwrap_or_default(),
        )
    }
}

fn first_intersection(local: &[String], remote: &[String]) -> Option<String> {
    for item in local {
        if remote.iter().any(|candidate| candidate == item) {
            return Some(item.clone());
        }
    }
    None
}
