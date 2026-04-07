// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::collections::HashMap;
use std::fs;

use regex::Regex;
use serde_json::{Map, Value};
use url::Url;

use crate::errors::{AcpError, AcpResult};
use crate::json_support;
use crate::transport_auth::{
    AuthConfig, auth_config_from_value, auth_parameter, ensure_allowed_auth_types,
    normalize_auth_config, serialize_auth_config,
};

pub const DEFAULT_AMQP_EXCHANGE: &str = "acp.exchange";
pub const DEFAULT_AMQP_EXCHANGE_TYPE: &str = "direct";

pub type AmqpMessageHandler = dyn FnMut(&Map<String, Value>) -> bool + Send;

#[derive(Debug, Clone)]
pub struct AmqpTransportClient {
    pub broker_url: String,
    pub exchange: String,
    pub exchange_type: String,
    pub timeout_seconds: u64,
    pub auth: Option<AuthConfig>,
}

impl AmqpTransportClient {
    pub fn new(
        broker_url: impl Into<String>,
        exchange: Option<String>,
        exchange_type: Option<String>,
        timeout_seconds: u64,
    ) -> AcpResult<Self> {
        Self::new_with_auth(broker_url, exchange, exchange_type, timeout_seconds, None)
    }

    pub fn new_with_auth(
        broker_url: impl Into<String>,
        exchange: Option<String>,
        exchange_type: Option<String>,
        timeout_seconds: u64,
        auth: Option<AuthConfig>,
    ) -> AcpResult<Self> {
        let broker_url = broker_url.into();
        if broker_url.trim().is_empty() {
            return Err(AcpError::InvalidArgument(
                "broker_url must be provided".to_string(),
            ));
        }
        let auth = normalize_auth_config(auth)?;
        Ok(Self {
            broker_url,
            exchange: exchange
                .as_deref()
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .unwrap_or(DEFAULT_AMQP_EXCHANGE)
                .to_string(),
            exchange_type: exchange_type
                .as_deref()
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .unwrap_or(DEFAULT_AMQP_EXCHANGE_TYPE)
                .to_string(),
            timeout_seconds: timeout_seconds.max(1),
            auth,
        })
    }

    pub fn agent_identifier_token(agent_id: &str) -> AcpResult<String> {
        let regex = Regex::new(r"^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$")
            .map_err(|e| AcpError::Validation(format!("invalid agent id regex: {e}")))?;
        let captures = regex
            .captures(agent_id)
            .ok_or_else(|| AcpError::Validation(format!("Invalid agent identifier: {agent_id}")))?;
        let name = captures
            .name("name")
            .map(|m| m.as_str().to_string())
            .ok_or_else(|| AcpError::Validation("agent id missing name".to_string()))?;
        let domain = captures.name("domain").map(|m| m.as_str().to_string());
        let base = if let Some(domain) = domain {
            format!("{name}.{domain}")
        } else {
            name
        };
        let normalized = base
            .chars()
            .map(|ch| {
                if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-') {
                    ch
                } else {
                    '.'
                }
            })
            .collect::<String>()
            .split('.')
            .filter(|part| !part.is_empty())
            .collect::<Vec<_>>()
            .join(".");
        Ok(if normalized.is_empty() {
            "unknown".to_string()
        } else {
            normalized
        })
    }

    pub fn queue_name_for_agent(agent_id: &str) -> AcpResult<String> {
        Ok(format!(
            "acp.agent.{}",
            Self::agent_identifier_token(agent_id)?
        ))
    }

    pub fn routing_key_for_agent(agent_id: &str) -> AcpResult<String> {
        Ok(format!("agent.{}", Self::agent_identifier_token(agent_id)?))
    }

    pub fn build_service_hint(
        agent_id: &str,
        broker_url: &str,
        exchange: Option<&str>,
    ) -> AcpResult<Map<String, Value>> {
        Self::build_service_hint_with_auth(agent_id, broker_url, exchange, None)
    }

    pub fn build_service_hint_with_auth(
        agent_id: &str,
        broker_url: &str,
        exchange: Option<&str>,
        auth: Option<AuthConfig>,
    ) -> AcpResult<Map<String, Value>> {
        let mut hint = Map::new();
        hint.insert(
            "broker_url".to_string(),
            Value::String(broker_url.to_string()),
        );
        hint.insert(
            "exchange".to_string(),
            Value::String(exchange.unwrap_or(DEFAULT_AMQP_EXCHANGE).to_string()),
        );
        hint.insert(
            "queue".to_string(),
            Value::String(Self::queue_name_for_agent(agent_id)?),
        );
        hint.insert(
            "routing_key".to_string(),
            Value::String(Self::routing_key_for_agent(agent_id)?),
        );
        if let Some(auth) = serialize_auth_config(normalize_auth_config(auth)?.as_ref()) {
            hint.insert("auth".to_string(), auth);
        }
        Ok(hint)
    }

    pub fn publish(
        &self,
        message: &Map<String, Value>,
        recipient_agent_id: &str,
        amqp_service: Option<&Map<String, Value>>,
    ) -> AcpResult<()> {
        let broker_url = pick_string(amqp_service, "broker_url", &self.broker_url);
        let auth = normalize_auth_config(
            auth_config_from_value(amqp_service.and_then(|map| map.get("auth")))?
                .or_else(|| self.auth.clone()),
        )?;
        ensure_allowed_auth_types(
            auth.as_ref(),
            &["none", "username_password", "mtls", "custom"],
            "AMQP transport",
        )?;
        let broker_url = broker_url_with_auth(&broker_url, auth.as_ref())?;
        let tls_config = amqp_tls_config(auth.as_ref())?;
        let exchange = pick_string(amqp_service, "exchange", &self.exchange);
        let queue = pick_string(
            amqp_service,
            "queue",
            &Self::queue_name_for_agent(recipient_agent_id)?,
        );
        let routing_key = pick_string(
            amqp_service,
            "routing_key",
            &Self::routing_key_for_agent(recipient_agent_id)?,
        );
        let headers = metadata_headers(message);
        let body = json_support::canonical_json_string(&Value::Object(message.clone()))?;
        let exchange_type = self.exchange_type.clone();
        let timeout = self.timeout_seconds;

        run_async(timeout, async move {
            use lapin::options::{
                BasicPublishOptions, ExchangeDeclareOptions, QueueBindOptions, QueueDeclareOptions,
            };
            use lapin::types::{AMQPValue, FieldTable, LongString, ShortString};
            use lapin::{BasicProperties, Connection, ConnectionProperties, ExchangeKind};

            let connection = if let Some(config) = tls_config {
                Connection::connect_with_config(
                    &broker_url,
                    ConnectionProperties::default(),
                    config,
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp connect failed: {e}")))?
            } else {
                Connection::connect(&broker_url, ConnectionProperties::default())
                    .await
                    .map_err(|e| AcpError::Transport(format!("amqp connect failed: {e}")))?
            };
            let channel = connection
                .create_channel()
                .await
                .map_err(|e| AcpError::Transport(format!("amqp channel failed: {e}")))?;
            let kind = match exchange_type.to_lowercase().as_str() {
                "fanout" => ExchangeKind::Fanout,
                "topic" => ExchangeKind::Topic,
                "headers" => ExchangeKind::Headers,
                _ => ExchangeKind::Direct,
            };
            channel
                .exchange_declare(
                    &exchange,
                    kind,
                    ExchangeDeclareOptions {
                        durable: true,
                        ..Default::default()
                    },
                    FieldTable::default(),
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp exchange declare failed: {e}")))?;
            channel
                .queue_declare(
                    &queue,
                    QueueDeclareOptions {
                        durable: true,
                        ..Default::default()
                    },
                    FieldTable::default(),
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp queue declare failed: {e}")))?;
            channel
                .queue_bind(
                    &queue,
                    &exchange,
                    &routing_key,
                    QueueBindOptions::default(),
                    FieldTable::default(),
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp queue bind failed: {e}")))?;
            let mut table = FieldTable::default();
            for (key, value) in headers {
                table.insert(
                    ShortString::from(key),
                    AMQPValue::LongString(LongString::from(value)),
                );
            }
            let properties = BasicProperties::default()
                .with_content_type(ShortString::from("application/json"))
                .with_delivery_mode(2)
                .with_headers(table);
            channel
                .basic_publish(
                    &exchange,
                    &routing_key,
                    BasicPublishOptions::default(),
                    body.as_bytes(),
                    properties,
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp publish failed: {e}")))?
                .await
                .map_err(|e| AcpError::Transport(format!("amqp publisher confirm failed: {e}")))?;
            connection
                .close(200, "ok")
                .await
                .map_err(|e| AcpError::Transport(format!("amqp close failed: {e}")))?;
            Ok(())
        })
    }

    pub fn consume<F>(
        &self,
        agent_id: &str,
        mut handler: F,
        amqp_service: Option<&Map<String, Value>>,
        max_messages: usize,
    ) -> AcpResult<usize>
    where
        F: FnMut(&Map<String, Value>) -> bool + Send + 'static,
    {
        let broker_url = pick_string(amqp_service, "broker_url", &self.broker_url);
        let auth = normalize_auth_config(
            auth_config_from_value(amqp_service.and_then(|map| map.get("auth")))?
                .or_else(|| self.auth.clone()),
        )?;
        ensure_allowed_auth_types(
            auth.as_ref(),
            &["none", "username_password", "mtls", "custom"],
            "AMQP transport",
        )?;
        let broker_url = broker_url_with_auth(&broker_url, auth.as_ref())?;
        let tls_config = amqp_tls_config(auth.as_ref())?;
        let exchange = pick_string(amqp_service, "exchange", &self.exchange);
        let queue = pick_string(
            amqp_service,
            "queue",
            &Self::queue_name_for_agent(agent_id)?,
        );
        let routing_key = pick_string(
            amqp_service,
            "routing_key",
            &Self::routing_key_for_agent(agent_id)?,
        );
        let limit = if max_messages == 0 {
            usize::MAX
        } else {
            max_messages
        };
        let exchange_type = self.exchange_type.clone();
        let timeout = self.timeout_seconds;

        run_async(timeout, async move {
            use lapin::options::{
                BasicAckOptions, BasicGetOptions, BasicNackOptions, ExchangeDeclareOptions,
                QueueBindOptions, QueueDeclareOptions,
            };
            use lapin::types::FieldTable;
            use lapin::{Connection, ConnectionProperties, ExchangeKind};
            let connection = if let Some(config) = tls_config {
                Connection::connect_with_config(
                    &broker_url,
                    ConnectionProperties::default(),
                    config,
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp connect failed: {e}")))?
            } else {
                Connection::connect(&broker_url, ConnectionProperties::default())
                    .await
                    .map_err(|e| AcpError::Transport(format!("amqp connect failed: {e}")))?
            };
            let channel = connection
                .create_channel()
                .await
                .map_err(|e| AcpError::Transport(format!("amqp channel failed: {e}")))?;
            let kind = match exchange_type.to_lowercase().as_str() {
                "fanout" => ExchangeKind::Fanout,
                "topic" => ExchangeKind::Topic,
                "headers" => ExchangeKind::Headers,
                _ => ExchangeKind::Direct,
            };
            channel
                .exchange_declare(
                    &exchange,
                    kind,
                    ExchangeDeclareOptions {
                        durable: true,
                        ..Default::default()
                    },
                    FieldTable::default(),
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp exchange declare failed: {e}")))?;
            channel
                .queue_declare(
                    &queue,
                    QueueDeclareOptions {
                        durable: true,
                        ..Default::default()
                    },
                    FieldTable::default(),
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp queue declare failed: {e}")))?;
            channel
                .queue_bind(
                    &queue,
                    &exchange,
                    &routing_key,
                    QueueBindOptions::default(),
                    FieldTable::default(),
                )
                .await
                .map_err(|e| AcpError::Transport(format!("amqp queue bind failed: {e}")))?;

            let mut processed = 0usize;
            while processed < limit {
                let delivery = channel
                    .basic_get(&queue, BasicGetOptions { no_ack: false })
                    .await
                    .map_err(|e| AcpError::Transport(format!("amqp basic_get failed: {e}")))?;
                let Some(delivery) = delivery else {
                    break;
                };
                let should_ack = std::str::from_utf8(&delivery.data)
                    .ok()
                    .and_then(|body| json_support::map_from_json(body).ok())
                    .map(|message| handler(&message))
                    .unwrap_or(false);
                if should_ack {
                    delivery
                        .ack(BasicAckOptions::default())
                        .await
                        .map_err(|e| AcpError::Transport(format!("amqp ack failed: {e}")))?;
                } else {
                    delivery
                        .nack(BasicNackOptions {
                            requeue: true,
                            ..Default::default()
                        })
                        .await
                        .map_err(|e| AcpError::Transport(format!("amqp nack failed: {e}")))?;
                }
                processed += 1;
            }
            connection
                .close(200, "ok")
                .await
                .map_err(|e| AcpError::Transport(format!("amqp close failed: {e}")))?;
            Ok(processed)
        })
    }
}

fn broker_url_with_auth(broker_url: &str, auth: Option<&AuthConfig>) -> AcpResult<String> {
    let Some(auth) = auth else {
        return Ok(broker_url.to_string());
    };
    if auth.auth_type != "username_password" && auth.auth_type != "custom" {
        return Ok(broker_url.to_string());
    }
    let username = if auth.auth_type == "username_password" {
        Some(auth_parameter(
            auth,
            "username",
            "AMQP username_password auth",
        )?)
    } else {
        auth.parameters
            .get("username")
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
    };
    let Some(username) = username else {
        return Ok(broker_url.to_string());
    };
    let password = if auth.auth_type == "username_password" {
        auth_parameter(auth, "password", "AMQP username_password auth")?
    } else {
        auth.parameters
            .get("password")
            .map(|value| value.trim().to_string())
            .unwrap_or_default()
    };
    let mut parsed = Url::parse(broker_url)?;
    parsed
        .set_username(&username)
        .map_err(|_| AcpError::Validation("invalid AMQP username".to_string()))?;
    parsed
        .set_password(Some(&password))
        .map_err(|_| AcpError::Validation("invalid AMQP password".to_string()))?;
    Ok(parsed.to_string())
}

fn amqp_tls_config(auth: Option<&AuthConfig>) -> AcpResult<Option<lapin::tcp::OwnedTLSConfig>> {
    let Some(auth) = auth else {
        return Ok(None);
    };
    if auth.auth_type == "mtls"
        || (auth.auth_type == "custom"
            && auth
                .parameters
                .get("cert_path")
                .map(|value| !value.trim().is_empty())
                .unwrap_or(false))
    {
        return Err(AcpError::Validation(
            "Rust AMQP mTLS currently requires PKCS#12 identity; cert_path/key_path PEM is not supported by this client"
                .to_string(),
        ));
    }
    let cert_chain = auth
        .parameters
        .get("ca_path")
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    let Some(cert_chain_path) = cert_chain else {
        return Ok(None);
    };
    let cert_chain = fs::read_to_string(&cert_chain_path).map_err(|e| {
        AcpError::Validation(format!("unable to read auth.parameters.ca_path: {e}"))
    })?;
    Ok(Some(lapin::tcp::OwnedTLSConfig {
        identity: None,
        cert_chain: Some(cert_chain),
    }))
}

fn metadata_headers(message: &Map<String, Value>) -> HashMap<String, String> {
    let mut headers = HashMap::new();
    if let Some(envelope) = message.get("envelope").and_then(Value::as_object) {
        for (src, dest) in [
            ("acp_version", "acp_version"),
            ("message_class", "acp_message_class"),
            ("message_id", "acp_message_id"),
            ("operation_id", "acp_operation_id"),
            ("sender", "acp_sender"),
        ] {
            if let Some(value) = envelope
                .get(src)
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|v| !v.is_empty())
            {
                headers.insert(dest.to_string(), value.to_string());
            }
        }
    }
    headers
}

fn pick_string(service: Option<&Map<String, Value>>, key: &str, fallback: &str) -> String {
    service
        .and_then(|map| map.get(key))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .unwrap_or(fallback)
        .to_string()
}

fn run_async<T>(
    timeout_seconds: u64,
    fut: impl std::future::Future<Output = AcpResult<T>> + Send + 'static,
) -> AcpResult<T>
where
    T: Send + 'static,
{
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .map_err(|e| AcpError::Transport(format!("failed to create tokio runtime: {e}")))?;
    runtime.block_on(async move {
        match tokio::time::timeout(std::time::Duration::from_secs(timeout_seconds.max(1)), fut)
            .await
        {
            Ok(result) => result,
            Err(_) => Err(AcpError::Transport("amqp operation timed out".to_string())),
        }
    })
}
