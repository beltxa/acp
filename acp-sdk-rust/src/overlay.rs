use std::sync::Arc;

use serde_json::{Map, Value};

use crate::agent::{AcpAgent, InboundHandlerFn};
use crate::errors::{AcpError, AcpResult, FailReason};
use crate::messages::{DeliveryMode, MessageClass, SendResult};

pub type BusinessHandler =
    Arc<dyn Fn(&Map<String, Value>) -> Option<Map<String, Value>> + Send + Sync>;
pub type PassthroughHandler =
    Arc<dyn Fn(&Map<String, Value>) -> Option<Map<String, Value>> + Send + Sync>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OverlayTarget {
    pub agent_id: String,
    pub base_url: String,
    pub well_known_url: String,
    pub identity_document_url: String,
}

#[derive(Debug, Clone)]
pub struct OverlaySendResult {
    pub target: Option<OverlayTarget>,
    pub send_result: SendResult,
}

#[derive(Clone)]
pub struct OverlayInboundAdapter {
    pub agent: AcpAgent,
    pub business_handler: BusinessHandler,
    pub passthrough_handler: Option<PassthroughHandler>,
}

impl OverlayInboundAdapter {
    pub fn new(
        agent: AcpAgent,
        business_handler: BusinessHandler,
        passthrough_handler: Option<PassthroughHandler>,
    ) -> Self {
        Self {
            agent,
            business_handler,
            passthrough_handler,
        }
    }

    pub fn handle_request(&mut self, body: &Map<String, Value>) -> AcpResult<Map<String, Value>> {
        if !is_acp_http_message(body) {
            if let Some(passthrough) = &self.passthrough_handler {
                let payload = passthrough(body).unwrap_or_default();
                let mut response = Map::new();
                response.insert("mode".to_string(), Value::String("passthrough".to_string()));
                response.insert("payload".to_string(), Value::Object(payload));
                return Ok(response);
            }
            return Err(AcpError::Validation(
                "Request is not an ACP message and no passthrough_handler is configured"
                    .to_string(),
            ));
        }
        let business_handler = self.business_handler.clone();
        let inbound_handler =
            move |payload: &Map<String, Value>, _envelope: &crate::messages::Envelope| {
                business_handler(payload)
            };
        let inbound = self
            .agent
            .receive(body, Some(&inbound_handler as &InboundHandlerFn));
        let mut response = Map::new();
        response.insert("mode".to_string(), Value::String("acp".to_string()));
        response.insert(
            "acp_result".to_string(),
            serde_json::to_value(&inbound).unwrap_or(Value::Null),
        );
        response.insert(
            "state".to_string(),
            Value::String(format!("{:?}", inbound.state).to_uppercase()),
        );
        if let Some(reason_code) = inbound.reason_code {
            response.insert("reason_code".to_string(), Value::String(reason_code));
        } else {
            response.insert("reason_code".to_string(), Value::Null);
        }
        if let Some(detail) = inbound.detail {
            response.insert("detail".to_string(), Value::String(detail));
        } else {
            response.insert("detail".to_string(), Value::Null);
        }
        response.insert(
            "response_message".to_string(),
            inbound
                .response_message
                .map(Value::Object)
                .unwrap_or(Value::Null),
        );
        Ok(response)
    }
}

#[derive(Clone)]
pub struct OverlayOutboundAdapter {
    pub agent: AcpAgent,
}

impl OverlayOutboundAdapter {
    pub fn new(agent: AcpAgent) -> Self {
        Self { agent }
    }

    pub fn resolve_target(
        &mut self,
        target_base_url: &str,
        expected_agent_id: Option<&str>,
    ) -> AcpResult<OverlayTarget> {
        let resolved = self
            .agent
            .resolve_well_known(target_base_url, expected_agent_id)?;
        let well_known = resolved
            .get("well_known")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                AcpError::Discovery(
                    "Resolved well-known metadata missing well_known object".to_string(),
                )
            })?;
        let identity_document = resolved
            .get("identity_document")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                AcpError::Discovery(
                    "Resolved well-known metadata missing identity_document object".to_string(),
                )
            })?;
        let agent_id = identity_document
            .get("agent_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .ok_or_else(|| {
                AcpError::Discovery(
                    "Resolved well-known metadata did not include a valid identity_document.agent_id"
                        .to_string(),
                )
            })?;
        let identity_document_url = well_known
            .get("identity_document")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .ok_or_else(|| {
                AcpError::Discovery(
                    "Resolved well-known metadata did not include a valid identity_document URL"
                        .to_string(),
                )
            })?;
        Ok(OverlayTarget {
            agent_id: agent_id.to_string(),
            base_url: target_base_url.trim_end_matches('/').to_string(),
            well_known_url: resolved
                .get("well_known_url")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            identity_document_url: identity_document_url.to_string(),
        })
    }

    #[allow(clippy::too_many_arguments)]
    pub fn send_business_payload(
        &mut self,
        payload: Map<String, Value>,
        target_base_url: Option<&str>,
        recipient_agent_id: Option<&str>,
        context: Option<String>,
        delivery_mode: Option<DeliveryMode>,
        expires_in_seconds: i64,
    ) -> AcpResult<OverlaySendResult> {
        let mut target = None;
        let mut resolved_recipient = recipient_agent_id.map(str::to_string);
        if let Some(target_base_url) = target_base_url {
            let resolved_target = self.resolve_target(target_base_url, recipient_agent_id)?;
            if resolved_recipient.is_none() {
                resolved_recipient = Some(resolved_target.agent_id.clone());
            }
            target = Some(resolved_target);
        }
        let recipient = resolved_recipient.ok_or_else(|| {
            AcpError::Validation(
                "send_business_payload requires recipient_agent_id or target_base_url for well-known bootstrap"
                    .to_string(),
            )
        })?;
        let send_result = self.agent.send(
            vec![recipient],
            payload,
            context,
            MessageClass::Send,
            expires_in_seconds,
            None,
            None,
            delivery_mode,
        )?;
        Ok(OverlaySendResult {
            target,
            send_result,
        })
    }
}

pub fn is_acp_http_message(body: &Map<String, Value>) -> bool {
    body.get("envelope").and_then(Value::as_object).is_some()
        && body.get("protected").and_then(Value::as_object).is_some()
}

pub fn invalid_overlay_request(detail: impl Into<String>) -> Map<String, Value> {
    let mut response = Map::new();
    response.insert("mode".to_string(), Value::String("invalid".to_string()));
    response.insert("state".to_string(), Value::String("FAILED".to_string()));
    response.insert(
        "reason_code".to_string(),
        Value::String(FailReason::PolicyRejected.as_str().to_string()),
    );
    response.insert("detail".to_string(), Value::String(detail.into()));
    response.insert("response_message".to_string(), Value::Null);
    response
}
