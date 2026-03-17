// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::time::{Duration, Instant};

use regex::Regex;
use rumqttc::{Client, Event, Incoming, MqttOptions, Outgoing, Packet, QoS, Transport};
use serde_json::{Map, Value};
use uuid::Uuid;

use crate::errors::{AcpError, AcpResult};
use crate::json_support;

pub const DEFAULT_MQTT_QOS: u8 = 1;
pub const DEFAULT_MQTT_TOPIC_PREFIX: &str = "acp/agent";

pub type MqttMessageHandler = dyn FnMut(&Map<String, Value>) -> bool + Send;

#[derive(Debug, Clone)]
pub struct MqttTransportClient {
    pub broker_url: String,
    pub qos: u8,
    pub topic_prefix: String,
    pub timeout_seconds: u64,
    pub keepalive_seconds: u16,
}

impl MqttTransportClient {
    pub fn new(
        broker_url: impl Into<String>,
        qos: Option<u8>,
        topic_prefix: Option<String>,
        timeout_seconds: u64,
        keepalive_seconds: u16,
    ) -> AcpResult<Self> {
        let broker_url = broker_url.into();
        if broker_url.trim().is_empty() {
            return Err(AcpError::InvalidArgument(
                "broker_url must be provided".to_string(),
            ));
        }
        Ok(Self {
            broker_url,
            qos: coerce_qos(qos.unwrap_or(DEFAULT_MQTT_QOS)),
            topic_prefix: topic_prefix
                .as_deref()
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .unwrap_or(DEFAULT_MQTT_TOPIC_PREFIX)
                .to_string(),
            timeout_seconds: timeout_seconds.max(1),
            keepalive_seconds: keepalive_seconds.max(5),
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
            .join(".")
            .to_lowercase();
        Ok(if normalized.is_empty() {
            "unknown".to_string()
        } else {
            normalized
        })
    }

    pub fn topic_for_agent(agent_id: &str, topic_prefix: Option<&str>) -> AcpResult<String> {
        let prefix = topic_prefix
            .unwrap_or(DEFAULT_MQTT_TOPIC_PREFIX)
            .trim_end_matches('/');
        Ok(format!(
            "{prefix}/{}",
            Self::agent_identifier_token(agent_id)?
        ))
    }

    pub fn build_service_hint(
        agent_id: &str,
        broker_url: &str,
        topic: Option<&str>,
        qos: Option<u8>,
        topic_prefix: Option<&str>,
    ) -> AcpResult<Map<String, Value>> {
        let mut hint = Map::new();
        hint.insert(
            "broker_url".to_string(),
            Value::String(broker_url.to_string()),
        );
        hint.insert(
            "topic".to_string(),
            Value::String(
                topic
                    .map(str::to_string)
                    .filter(|v| !v.trim().is_empty())
                    .unwrap_or(Self::topic_for_agent(agent_id, topic_prefix)?),
            ),
        );
        hint.insert(
            "qos".to_string(),
            Value::Number(coerce_qos(qos.unwrap_or(DEFAULT_MQTT_QOS)).into()),
        );
        Ok(hint)
    }

    pub fn publish(
        &self,
        message: &Map<String, Value>,
        recipient_agent_id: &str,
        mqtt_service: Option<&Map<String, Value>>,
    ) -> AcpResult<()> {
        let broker_url = pick_string(mqtt_service, "broker_url", &self.broker_url);
        let topic = pick_string(
            mqtt_service,
            "topic",
            &Self::topic_for_agent(recipient_agent_id, Some(&self.topic_prefix))?,
        );
        let qos = mqtt_service
            .and_then(|m| m.get("qos"))
            .and_then(value_as_u8)
            .map(coerce_qos)
            .unwrap_or(self.qos);
        let payload = json_support::canonical_json_string(&Value::Object(message.clone()))?;

        let (client, mut connection) = self.open_client(&broker_url)?;
        client
            .publish(topic, to_qos(qos), false, payload)
            .map_err(|e| AcpError::Transport(format!("mqtt publish failed: {e}")))?;
        let deadline = Instant::now() + Duration::from_secs(self.timeout_seconds.max(1));
        while Instant::now() < deadline {
            match connection.iter().next() {
                Some(Ok(Event::Incoming(Incoming::PubAck(_)))) => break,
                Some(Ok(Event::Outgoing(Outgoing::Publish(_)))) => break,
                Some(Ok(_)) => continue,
                Some(Err(e)) => {
                    return Err(AcpError::Transport(format!("mqtt event loop error: {e}")));
                }
                None => break,
            }
        }
        Ok(())
    }

    pub fn consume<F>(
        &self,
        agent_id: &str,
        mut handler: F,
        mqtt_service: Option<&Map<String, Value>>,
        max_messages: usize,
        poll_timeout: Duration,
    ) -> AcpResult<usize>
    where
        F: FnMut(&Map<String, Value>) -> bool + Send,
    {
        let broker_url = pick_string(mqtt_service, "broker_url", &self.broker_url);
        let topic = pick_string(
            mqtt_service,
            "topic",
            &Self::topic_for_agent(agent_id, Some(&self.topic_prefix))?,
        );
        let qos = mqtt_service
            .and_then(|m| m.get("qos"))
            .and_then(value_as_u8)
            .map(coerce_qos)
            .unwrap_or(self.qos);
        let limit = if max_messages == 0 {
            usize::MAX
        } else {
            max_messages
        };
        let (client, mut connection) = self.open_client(&broker_url)?;
        client
            .subscribe(topic, to_qos(qos))
            .map_err(|e| AcpError::Transport(format!("mqtt subscribe failed: {e}")))?;
        let mut processed = 0usize;
        let start = Instant::now();
        while processed < limit {
            if start.elapsed() >= poll_timeout {
                break;
            }
            match connection.iter().next() {
                Some(Ok(Event::Incoming(Packet::Publish(publish)))) => {
                    let should_ack = std::str::from_utf8(&publish.payload)
                        .ok()
                        .and_then(|body| json_support::map_from_json(body).ok())
                        .map(|message| handler(&message))
                        .unwrap_or(false);
                    let _ = should_ack;
                    processed += 1;
                }
                Some(Ok(_)) => continue,
                Some(Err(e)) => {
                    return Err(AcpError::Transport(format!("mqtt consume failed: {e}")));
                }
                None => break,
            }
        }
        Ok(processed)
    }

    fn open_client(&self, broker_url: &str) -> AcpResult<(Client, rumqttc::Connection)> {
        let parsed = url::Url::parse(broker_url)?;
        let host = parsed.host_str().ok_or_else(|| {
            AcpError::Validation(format!("Invalid MQTT broker_url: {broker_url}"))
        })?;
        let scheme = parsed.scheme().to_lowercase();
        let port = parsed.port().unwrap_or(match scheme.as_str() {
            "mqtts" | "ssl" | "wss" => 8883,
            _ => 1883,
        });
        let mut options = MqttOptions::new(format!("acp-{}", Uuid::new_v4().simple()), host, port);
        options.set_keep_alive(Duration::from_secs(u64::from(self.keepalive_seconds)));
        options.set_request_channel_capacity(16);
        if !parsed.username().is_empty() {
            options.set_credentials(parsed.username(), parsed.password().unwrap_or_default());
        }
        if matches!(scheme.as_str(), "mqtts" | "ssl" | "wss") {
            options.set_transport(Transport::tls_with_default_config());
        }
        Ok(Client::new(options, 10))
    }
}

fn to_qos(value: u8) -> QoS {
    match value {
        0 => QoS::AtMostOnce,
        2 => QoS::ExactlyOnce,
        _ => QoS::AtLeastOnce,
    }
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

fn coerce_qos(value: u8) -> u8 {
    if value > 2 { DEFAULT_MQTT_QOS } else { value }
}

fn value_as_u8(value: &Value) -> Option<u8> {
    if let Some(number) = value.as_u64() {
        return Some(number.min(2) as u8);
    }
    if let Some(text) = value.as_str() {
        return text.parse::<u8>().ok().map(|v| v.min(2));
    }
    None
}
