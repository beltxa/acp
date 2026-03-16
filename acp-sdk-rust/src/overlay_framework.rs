use std::sync::Arc;

use serde_json::{Map, Value};

use crate::agent::AcpAgent;
use crate::errors::{AcpError, AcpResult};
use crate::messages::DeliveryMode;
use crate::overlay::{
    BusinessHandler, OverlayInboundAdapter, OverlayOutboundAdapter, PassthroughHandler,
    invalid_overlay_request,
};

pub const WELL_KNOWN_CACHE_CONTROL: &str = "public, max-age=300";

#[derive(Debug, Clone)]
pub struct OverlayHttpResponse {
    pub status_code: u16,
    pub body: Map<String, Value>,
}

#[derive(Clone)]
pub struct OverlayFrameworkRuntime {
    pub agent: AcpAgent,
    pub base_url: String,
    pub inbound_adapter: OverlayInboundAdapter,
    pub outbound_adapter: OverlayOutboundAdapter,
}

#[derive(Clone)]
pub struct OverlayConfig {
    pub agent: AcpAgent,
    pub base_url: String,
    pub passthrough_handler: Option<PassthroughHandler>,
}

#[derive(Clone)]
pub struct OverlayClient {
    pub agent: AcpAgent,
    pub outbound_adapter: OverlayOutboundAdapter,
}

impl OverlayFrameworkRuntime {
    pub fn create(
        agent: AcpAgent,
        base_url: &str,
        business_handler: BusinessHandler,
        passthrough_handler: Option<PassthroughHandler>,
    ) -> AcpResult<Self> {
        let normalized_base_url = base_url.trim();
        if normalized_base_url.is_empty() {
            return Err(AcpError::Validation("base_url is required".to_string()));
        }
        let inbound_adapter =
            OverlayInboundAdapter::new(agent.clone(), business_handler, passthrough_handler);
        let outbound_adapter = OverlayOutboundAdapter::new(agent.clone());
        Ok(Self {
            agent,
            base_url: normalized_base_url.trim_end_matches('/').to_string(),
            inbound_adapter,
            outbound_adapter,
        })
    }

    pub fn handle_message_body(&mut self, body: &Value) -> OverlayHttpResponse {
        let Some(body) = body.as_object() else {
            return OverlayHttpResponse {
                status_code: 400,
                body: invalid_overlay_request("Expected JSON object request body"),
            };
        };
        match self.inbound_adapter.handle_request(body) {
            Ok(response) => OverlayHttpResponse {
                status_code: 200,
                body: response,
            },
            Err(exc) => OverlayHttpResponse {
                status_code: 400,
                body: invalid_overlay_request(exc.to_string()),
            },
        }
    }

    pub fn well_known_document(&self) -> AcpResult<Map<String, Value>> {
        self.agent
            .build_well_known_document(Some(&self.base_url), None)
    }

    pub fn well_known_headers() -> Map<String, Value> {
        let mut headers = Map::new();
        headers.insert(
            "Cache-Control".to_string(),
            Value::String(WELL_KNOWN_CACHE_CONTROL.to_string()),
        );
        headers
    }

    pub fn identity_document_payload(&self) -> Map<String, Value> {
        let mut payload = Map::new();
        payload.insert(
            "identity_document".to_string(),
            Value::Object(self.agent.identity_document.clone()),
        );
        payload
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
    ) -> AcpResult<Map<String, Value>> {
        let result = self.outbound_adapter.send_business_payload(
            payload,
            target_base_url,
            recipient_agent_id,
            context,
            delivery_mode,
            expires_in_seconds,
        )?;
        Ok(send_result_to_map(result))
    }

    pub fn send_acp(
        &mut self,
        target_url: &str,
        payload: Map<String, Value>,
        recipient_agent_id: Option<&str>,
        context: Option<String>,
        delivery_mode: Option<DeliveryMode>,
        expires_in_seconds: i64,
    ) -> AcpResult<Map<String, Value>> {
        self.send_business_payload(
            payload,
            Some(target_url),
            recipient_agent_id,
            context,
            delivery_mode,
            expires_in_seconds,
        )
    }

    pub fn handle(
        request_body: &Value,
        business_handler: BusinessHandler,
        config: OverlayConfig,
    ) -> OverlayHttpResponse {
        let runtime = Self::create(
            config.agent,
            &config.base_url,
            business_handler,
            config.passthrough_handler,
        );
        match runtime {
            Ok(mut runtime) => runtime.handle_message_body(request_body),
            Err(exc) => OverlayHttpResponse {
                status_code: 400,
                body: invalid_overlay_request(exc.to_string()),
            },
        }
    }
}

impl OverlayClient {
    pub fn create(agent: AcpAgent) -> Self {
        Self {
            outbound_adapter: OverlayOutboundAdapter::new(agent.clone()),
            agent,
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn send_acp(
        &mut self,
        target_url: &str,
        payload: Map<String, Value>,
        recipient_agent_id: Option<&str>,
        context: Option<String>,
        delivery_mode: Option<DeliveryMode>,
        expires_in_seconds: i64,
    ) -> AcpResult<Map<String, Value>> {
        let result = self.outbound_adapter.send_business_payload(
            payload,
            Some(target_url),
            recipient_agent_id,
            context,
            delivery_mode,
            expires_in_seconds,
        )?;
        Ok(send_result_to_map(result))
    }
}

pub fn acp_overlay_inbound(
    mut agent: AcpAgent,
    handler: Arc<dyn Fn(&Map<String, Value>) -> Option<Map<String, Value>> + Send + Sync>,
    passthrough: bool,
) -> impl FnMut(&Map<String, Value>) -> AcpResult<Map<String, Value>> {
    let passthrough_handler = if passthrough {
        Some(handler.clone())
    } else {
        None
    };
    move |payload: &Map<String, Value>| {
        let mut inbound =
            OverlayInboundAdapter::new(agent.clone(), handler.clone(), passthrough_handler.clone());
        let response = inbound.handle_request(payload);
        agent = inbound.agent;
        response
    }
}

fn send_result_to_map(result: crate::overlay::OverlaySendResult) -> Map<String, Value> {
    let mut map = Map::new();
    if let Some(target) = result.target {
        map.insert(
            "target".to_string(),
            serde_json::json!({
                "agent_id": target.agent_id,
                "base_url": target.base_url,
                "well_known_url": target.well_known_url,
                "identity_document_url": target.identity_document_url,
            }),
        );
    } else {
        map.insert("target".to_string(), Value::Null);
    }
    map.insert(
        "send_result".to_string(),
        serde_json::to_value(&result.send_result).unwrap_or(Value::Null),
    );
    map
}
