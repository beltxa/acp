// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::time::Duration;

use base64::Engine;
use serde_json::{Map, Value};

use crate::errors::{AcpError, AcpResult};
use crate::http_security::{HttpSecurityPolicy, build_http_client, validate_http_url};
use crate::messages::AcpMessage;
use crate::transport_auth::{
    AuthConfig, TransportConfig, auth_parameter, ensure_allowed_auth_types, normalize_auth_config,
};

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
    policy: HttpSecurityPolicy,
    allow_insecure_http: bool,
    default_auth: Option<AuthConfig>,
}

impl TransportClient {
    pub fn new(timeout_seconds: u64, policy: &HttpSecurityPolicy) -> AcpResult<Self> {
        Self::new_with_auth(timeout_seconds, policy, None)
    }

    pub fn new_with_auth(
        timeout_seconds: u64,
        policy: &HttpSecurityPolicy,
        auth: Option<AuthConfig>,
    ) -> AcpResult<Self> {
        let default_auth = normalize_auth_config(auth)?;
        let client = build_http_client(timeout_seconds.max(1), policy)?;
        Ok(Self {
            client,
            timeout_seconds: timeout_seconds.max(1),
            policy: policy.clone(),
            allow_insecure_http: policy.allow_insecure_http,
            default_auth,
        })
    }

    pub fn post_json(&self, url: &str, body: &Map<String, Value>) -> AcpResult<TransportResponse> {
        self.post_json_with_config(url, body, None)
    }

    pub fn post_json_with_config(
        &self,
        url: &str,
        body: &Map<String, Value>,
        config: Option<&TransportConfig>,
    ) -> AcpResult<TransportResponse> {
        let auth = normalize_auth_config(
            config
                .and_then(|cfg| cfg.auth.clone())
                .or_else(|| self.default_auth.clone()),
        )?;
        ensure_allowed_auth_types(
            auth.as_ref(),
            &["none", "bearer", "basic", "mtls", "custom"],
            "HTTP/relay transport",
        )?;
        let effective_mtls = self.policy.mtls_enabled
            || auth
                .as_ref()
                .map(|a| a.auth_type.as_str() == "mtls")
                .unwrap_or(false);
        validate_http_url(
            url,
            self.allow_insecure_http,
            effective_mtls,
            "HTTP transport request",
        )?;
        let http_client = if auth
            .as_ref()
            .map(|a| a.auth_type.as_str() == "mtls")
            .unwrap_or(false)
        {
            let auth = auth.as_ref().expect("auth exists for mtls branch");
            let cert_file = auth_parameter(auth, "cert_path", "mTLS auth")?;
            let key_file = auth_parameter(auth, "key_path", "mTLS auth")?;
            let mut policy = self.policy.clone();
            policy.mtls_enabled = true;
            policy.cert_file = Some(cert_file);
            policy.key_file = Some(key_file);
            if let Some(ca_path) = auth
                .parameters
                .get("ca_path")
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
            {
                policy.ca_file = Some(ca_path);
            }
            build_http_client(self.timeout_seconds, &policy)?
        } else {
            self.client.clone()
        };
        let mut request = http_client
            .post(url)
            .header("Content-Type", "application/json")
            .timeout(Duration::from_secs(self.timeout_seconds))
            .json(body);
        for (key, value) in http_auth_headers(auth.as_ref())? {
            request = request.header(key, value);
        }
        let response = self
            .client
            .execute(request.build()?)
            .map_err(|e| AcpError::Transport(format!("HTTP request failed: {e}")))?;
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
        self.send_to_relay_with_config(relay_url, message, None)
    }

    pub fn send_to_relay_with_config(
        &self,
        relay_url: &str,
        message: &AcpMessage,
        config: Option<&TransportConfig>,
    ) -> AcpResult<Map<String, Value>> {
        let relay_endpoint = if relay_url.ends_with('/') {
            format!("{relay_url}messages")
        } else {
            format!("{relay_url}/messages")
        };
        let response = self.post_json_with_config(&relay_endpoint, &message.to_map()?, config)?;
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

fn http_auth_headers(auth: Option<&AuthConfig>) -> AcpResult<Vec<(String, String)>> {
    let Some(auth) = auth else {
        return Ok(vec![]);
    };
    if matches!(auth.auth_type.as_str(), "none" | "mtls") {
        return Ok(vec![]);
    }
    match auth.auth_type.as_str() {
        "bearer" => {
            let token = auth_parameter(auth, "token", "Bearer auth")?;
            Ok(vec![(
                "Authorization".to_string(),
                format!("Bearer {token}"),
            )])
        }
        "basic" => {
            let username = auth_parameter(auth, "username", "Basic auth")?;
            let password = auth_parameter(auth, "password", "Basic auth")?;
            let encoded = base64::engine::general_purpose::STANDARD
                .encode(format!("{username}:{password}").as_bytes());
            Ok(vec![(
                "Authorization".to_string(),
                format!("Basic {encoded}"),
            )])
        }
        "custom" => {
            let header = auth
                .parameters
                .get("header")
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty());
            let value = auth
                .parameters
                .get("value")
                .map(|item| item.trim().to_string())
                .filter(|item| !item.is_empty());
            let scheme = auth
                .parameters
                .get("scheme")
                .map(|item| item.trim().to_string())
                .filter(|item| !item.is_empty());
            if let Some(header) = header {
                let value = value.ok_or_else(|| {
                    AcpError::Validation(
                        "Custom auth requires auth.parameters.value when header is set".to_string(),
                    )
                })?;
                return Ok(vec![(header, value)]);
            }
            if let Some(scheme) = scheme {
                let value = value.ok_or_else(|| {
                    AcpError::Validation(
                        "Custom auth requires auth.parameters.value when scheme is set".to_string(),
                    )
                })?;
                return Ok(vec![(
                    "Authorization".to_string(),
                    format!("{scheme} {value}"),
                )]);
            }
            Err(AcpError::Validation(
                "Custom auth requires either parameters.header + parameters.value or parameters.scheme + parameters.value".to_string(),
            ))
        }
        _ => Err(AcpError::Validation(format!(
            "HTTP/relay transport does not support auth type: {}",
            auth.auth_type
        ))),
    }
}
