use std::time::Duration;

use serde_json::{Map, Value};

use crate::errors::{AcpError, AcpResult};
use crate::http_security::{HttpSecurityPolicy, build_http_client, validate_http_url};
use crate::messages::AcpMessage;

#[derive(Debug, Clone)]
pub struct TransportResponse {
    pub status_code: u16,
    pub body: Option<Map<String, Value>>,
    pub raw_body: String,
}

#[derive(Debug, Clone)]
pub struct TransportClient {
    client: reqwest::blocking::Client,
    timeout_seconds: u64,
    allow_insecure_http: bool,
    mtls_enabled: bool,
}

impl TransportClient {
    pub fn new(timeout_seconds: u64, policy: &HttpSecurityPolicy) -> AcpResult<Self> {
        let client = build_http_client(timeout_seconds.max(1), policy)?;
        Ok(Self {
            client,
            timeout_seconds: timeout_seconds.max(1),
            allow_insecure_http: policy.allow_insecure_http,
            mtls_enabled: policy.mtls_enabled,
        })
    }

    pub fn post_json(&self, url: &str, body: &Map<String, Value>) -> AcpResult<TransportResponse> {
        validate_http_url(
            url,
            self.allow_insecure_http,
            self.mtls_enabled,
            "HTTP transport request",
        )?;
        let response = self
            .client
            .post(url)
            .header("Content-Type", "application/json")
            .timeout(Duration::from_secs(self.timeout_seconds))
            .json(body)
            .send()?;
        let status_code = response.status().as_u16();
        let raw_body = response.text().unwrap_or_default();
        let body = serde_json::from_str::<Value>(&raw_body)
            .ok()
            .and_then(|value| value.as_object().cloned());
        Ok(TransportResponse {
            status_code,
            body,
            raw_body,
        })
    }

    pub fn send_to_relay(
        &self,
        relay_url: &str,
        message: &AcpMessage,
    ) -> AcpResult<Map<String, Value>> {
        let relay_endpoint = if relay_url.ends_with('/') {
            format!("{relay_url}messages")
        } else {
            format!("{relay_url}/messages")
        };
        let response = self.post_json(&relay_endpoint, &message.to_map()?)?;
        if response.status_code != 200 {
            return Err(AcpError::Transport(format!(
                "Relay returned HTTP {} for message {}",
                response.status_code, message.envelope.message_id
            )));
        }
        response
            .body
            .ok_or_else(|| AcpError::Transport("Relay returned non-JSON response".to_string()))
    }
}
