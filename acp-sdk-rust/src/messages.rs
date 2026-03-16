use chrono::{Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use uuid::Uuid;

use crate::constants::{ACP_VERSION, DEFAULT_CRYPTO_SUITE};
use crate::errors::{AcpError, AcpResult};
use crate::json_support::{self, JsonMap};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MessageClass {
    Send,
    Ack,
    Fail,
    Capabilities,
    Compensate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum DeliveryState {
    Pending,
    Delivered,
    Acknowledged,
    Failed,
    Declined,
    Expired,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum DeliveryMode {
    Auto,
    Direct,
    Relay,
    Amqp,
    Mqtt,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WrappedContentKey {
    pub recipient: String,
    #[serde(rename = "ephemeral_public_key")]
    pub ephemeral_public_key: String,
    pub nonce: String,
    pub ciphertext: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Envelope {
    #[serde(rename = "acp_version")]
    pub acp_version: String,
    #[serde(rename = "message_class")]
    pub message_class: MessageClass,
    #[serde(rename = "message_id")]
    pub message_id: String,
    #[serde(rename = "operation_id")]
    pub operation_id: String,
    pub timestamp: String,
    #[serde(rename = "expires_at")]
    pub expires_at: String,
    pub sender: String,
    pub recipients: Vec<String>,
    #[serde(rename = "context_id")]
    pub context_id: String,
    #[serde(rename = "crypto_suite")]
    pub crypto_suite: String,
    #[serde(
        rename = "correlation_id",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub correlation_id: Option<String>,
    #[serde(
        rename = "in_reply_to",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub in_reply_to: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProtectedPayload {
    pub nonce: String,
    pub ciphertext: String,
    #[serde(rename = "wrapped_content_keys")]
    pub wrapped_content_keys: Vec<WrappedContentKey>,
    #[serde(rename = "payload_hash")]
    pub payload_hash: String,
    #[serde(rename = "signature_kid")]
    pub signature_kid: String,
    pub signature: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AcpMessage {
    pub envelope: Envelope,
    #[serde(rename = "protected")]
    pub protected_payload: ProtectedPayload,
    #[serde(
        rename = "sender_identity_document",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub sender_identity_document: Option<JsonMap>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DeliveryOutcome {
    pub recipient: String,
    pub state: DeliveryState,
    #[serde(
        rename = "status_code",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub status_code: Option<u16>,
    #[serde(
        rename = "response_class",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub response_class: Option<MessageClass>,
    #[serde(
        rename = "reason_code",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub reason_code: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    #[serde(
        rename = "response_message",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub response_message: Option<JsonMap>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SendResult {
    #[serde(rename = "operation_id")]
    pub operation_id: String,
    #[serde(rename = "message_id")]
    pub message_id: String,
    #[serde(rename = "message_ids", default, skip_serializing_if = "Vec::is_empty")]
    pub message_ids: Vec<String>,
    #[serde(default)]
    pub outcomes: Vec<DeliveryOutcome>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CompensateInstruction {
    #[serde(rename = "operation_id")]
    pub operation_id: String,
    pub reason: String,
    #[serde(default)]
    pub actions: Vec<JsonMap>,
}

impl Envelope {
    #[allow(clippy::too_many_arguments)]
    pub fn build(
        sender: impl Into<String>,
        recipients: Vec<String>,
        message_class: MessageClass,
        context_id: impl Into<String>,
        expires_in_seconds: i64,
        operation_id: Option<String>,
        correlation_id: Option<String>,
        in_reply_to: Option<String>,
        crypto_suite: Option<String>,
    ) -> AcpResult<Self> {
        let now = Utc::now();
        let expires_at = now + Duration::seconds(expires_in_seconds.max(1));
        let env = Self {
            acp_version: ACP_VERSION.to_string(),
            message_class,
            message_id: Uuid::new_v4().to_string(),
            operation_id: operation_id.unwrap_or_else(|| Uuid::new_v4().to_string()),
            timestamp: now.to_rfc3339(),
            expires_at: expires_at.to_rfc3339(),
            sender: sender.into(),
            recipients,
            context_id: context_id.into(),
            crypto_suite: crypto_suite.unwrap_or_else(|| DEFAULT_CRYPTO_SUITE.to_string()),
            correlation_id,
            in_reply_to,
        };
        env.validate()?;
        Ok(env)
    }

    pub fn validate(&self) -> AcpResult<()> {
        if self.sender.trim().is_empty() {
            return Err(AcpError::Validation(
                "Envelope sender is required".to_string(),
            ));
        }
        if self.recipients.is_empty() {
            return Err(AcpError::Validation(
                "Envelope recipients must not be empty".to_string(),
            ));
        }
        let ts = chrono::DateTime::parse_from_rfc3339(&self.timestamp)
            .map_err(|e| AcpError::Validation(format!("Invalid timestamp: {e}")))?;
        let exp = chrono::DateTime::parse_from_rfc3339(&self.expires_at)
            .map_err(|e| AcpError::Validation(format!("Invalid expires_at: {e}")))?;
        if exp <= ts {
            return Err(AcpError::Validation(
                "Envelope expires_at must be after timestamp".to_string(),
            ));
        }
        Ok(())
    }

    pub fn is_expired(&self) -> bool {
        chrono::DateTime::parse_from_rfc3339(&self.expires_at)
            .map(|exp| exp <= Utc::now())
            .unwrap_or(true)
    }

    pub fn to_map(&self) -> AcpResult<JsonMap> {
        json_support::to_map(self)
    }
}

impl ProtectedPayload {
    pub fn to_signable_value(&self) -> Value {
        let mut keys = self.wrapped_content_keys.clone();
        keys.sort_by(|a, b| a.recipient.cmp(&b.recipient));
        json!({
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
            "wrapped_content_keys": keys,
            "payload_hash": self.payload_hash,
            "signature_kid": self.signature_kid,
        })
    }
}

impl AcpMessage {
    pub fn to_map(&self) -> AcpResult<JsonMap> {
        json_support::to_map(self)
    }

    pub fn from_map(value: &JsonMap) -> AcpResult<Self> {
        serde_json::from_value(Value::Object(value.clone())).map_err(AcpError::from)
    }

    pub fn to_json(&self) -> AcpResult<String> {
        let value = serde_json::to_value(self)?;
        json_support::canonical_json_string(&value)
    }
}

impl SendResult {
    pub fn to_map(&self) -> AcpResult<JsonMap> {
        json_support::to_map(self)
    }
}

pub fn build_ack_payload(
    received_message_id: impl Into<String>,
    status: impl Into<String>,
) -> JsonMap {
    let mut payload = JsonMap::new();
    payload.insert("status".to_string(), Value::String(status.into()));
    payload.insert(
        "received_message_id".to_string(),
        Value::String(received_message_id.into()),
    );
    payload
}

pub fn build_fail_payload(
    reason_code: impl Into<String>,
    detail: impl Into<String>,
    retriable: bool,
) -> JsonMap {
    let mut payload = JsonMap::new();
    payload.insert("reason_code".to_string(), Value::String(reason_code.into()));
    payload.insert("detail".to_string(), Value::String(detail.into()));
    payload.insert("retriable".to_string(), Value::Bool(retriable));
    payload
}
