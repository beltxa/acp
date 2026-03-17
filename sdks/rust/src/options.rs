// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use serde_json::{Map, Value};

use crate::amqp_transport::{
    AmqpTransportClient, DEFAULT_AMQP_EXCHANGE, DEFAULT_AMQP_EXCHANGE_TYPE,
};
use crate::capabilities::AgentCapabilities;
use crate::key_provider::KeyProvider;
use crate::messages::DeliveryMode;
use crate::mqtt_transport::{DEFAULT_MQTT_QOS, DEFAULT_MQTT_TOPIC_PREFIX, MqttTransportClient};

#[derive(Clone)]
pub struct AcpAgentOptions {
    pub storage_dir: PathBuf,
    pub endpoint: Option<String>,
    pub relay_url: String,
    pub relay_hints: Vec<String>,
    pub enterprise_directory_hints: Vec<String>,
    pub discovery_scheme: String,
    pub trust_profile: String,
    pub capabilities: Option<AgentCapabilities>,
    pub default_delivery_mode: DeliveryMode,
    pub http_timeout_seconds: u64,
    pub allow_insecure_http: bool,
    pub allow_insecure_tls: bool,
    pub mtls_enabled: bool,
    pub ca_file: Option<String>,
    pub cert_file: Option<String>,
    pub key_file: Option<String>,
    pub key_provider: String,
    pub vault_url: Option<String>,
    pub vault_path: Option<String>,
    pub vault_token_env: String,
    pub vault_token: Option<String>,
    pub key_provider_instance: Option<Arc<dyn KeyProvider>>,
    pub amqp_broker_url: Option<String>,
    pub amqp_exchange: String,
    pub amqp_exchange_type: String,
    pub amqp_transport: Option<AmqpTransportClient>,
    pub mqtt_broker_url: Option<String>,
    pub mqtt_qos: u8,
    pub mqtt_topic_prefix: String,
    pub mqtt_transport: Option<MqttTransportClient>,
    pub extra: HashMap<String, Value>,
}

impl Default for AcpAgentOptions {
    fn default() -> Self {
        Self {
            storage_dir: PathBuf::from(".acp-data"),
            endpoint: None,
            relay_url: "https://localhost:8080".to_string(),
            relay_hints: Vec::new(),
            enterprise_directory_hints: Vec::new(),
            discovery_scheme: "https".to_string(),
            trust_profile: "self_asserted".to_string(),
            capabilities: None,
            default_delivery_mode: DeliveryMode::Auto,
            http_timeout_seconds: 10,
            allow_insecure_http: false,
            allow_insecure_tls: false,
            mtls_enabled: false,
            ca_file: None,
            cert_file: None,
            key_file: None,
            key_provider: "local".to_string(),
            vault_url: None,
            vault_path: None,
            vault_token_env: "VAULT_TOKEN".to_string(),
            vault_token: None,
            key_provider_instance: None,
            amqp_broker_url: None,
            amqp_exchange: DEFAULT_AMQP_EXCHANGE.to_string(),
            amqp_exchange_type: DEFAULT_AMQP_EXCHANGE_TYPE.to_string(),
            amqp_transport: None,
            mqtt_broker_url: None,
            mqtt_qos: DEFAULT_MQTT_QOS,
            mqtt_topic_prefix: DEFAULT_MQTT_TOPIC_PREFIX.to_string(),
            mqtt_transport: None,
            extra: HashMap::new(),
        }
    }
}

impl AcpAgentOptions {
    pub fn to_config_map(&self) -> Map<String, Value> {
        let mut values = Map::new();
        values.insert(
            "allow_insecure_http".to_string(),
            Value::Bool(self.allow_insecure_http),
        );
        values.insert(
            "allow_insecure_tls".to_string(),
            Value::Bool(self.allow_insecure_tls),
        );
        values.insert("mtls_enabled".to_string(), Value::Bool(self.mtls_enabled));
        values.insert(
            "ca_file".to_string(),
            self.ca_file
                .clone()
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        values.insert(
            "cert_file".to_string(),
            self.cert_file
                .clone()
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        values.insert(
            "key_file".to_string(),
            self.key_file
                .clone()
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        values.insert(
            "key_provider".to_string(),
            Value::String(self.key_provider.clone()),
        );
        values.insert(
            "vault_url".to_string(),
            self.vault_url
                .clone()
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        values.insert(
            "vault_path".to_string(),
            self.vault_path
                .clone()
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        values.insert(
            "vault_token_env".to_string(),
            Value::String(self.vault_token_env.clone()),
        );
        values
    }

    pub fn from_config_map(config: Option<&Map<String, Value>>) -> Self {
        let mut options = Self::default();
        let Some(config) = config else {
            return options;
        };
        options.allow_insecure_http = as_bool(config.get("allow_insecure_http"), false);
        options.allow_insecure_tls = as_bool(config.get("allow_insecure_tls"), false);
        options.mtls_enabled = as_bool(config.get("mtls_enabled"), false);
        options.ca_file = as_string(config.get("ca_file"));
        options.cert_file = as_string(config.get("cert_file"));
        options.key_file = as_string(config.get("key_file"));
        options.key_provider =
            as_string(config.get("key_provider")).unwrap_or_else(|| "local".to_string());
        options.vault_url = as_string(config.get("vault_url"));
        options.vault_path = as_string(config.get("vault_path"));
        options.vault_token_env =
            as_string(config.get("vault_token_env")).unwrap_or_else(|| "VAULT_TOKEN".to_string());
        options
    }
}

fn as_bool(value: Option<&Value>, default_value: bool) -> bool {
    match value {
        Some(Value::Bool(v)) => *v,
        Some(Value::String(v)) => match v.trim().to_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => default_value,
        },
        _ => default_value,
    }
}

fn as_string(value: Option<&Value>) -> Option<String> {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_string)
}
