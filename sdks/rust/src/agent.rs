// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::{Map, Value};
use uuid::Uuid;

use crate::amqp_transport::AmqpTransportClient;
use crate::capabilities::AgentCapabilities;
use crate::constants::{ACP_VERSION, DEFAULT_CRYPTO_SUITE};
use crate::crypto;
use crate::discovery::DiscoveryClient;
use crate::errors::{AcpError, AcpResult, FailReason};
use crate::http_security::{HttpSecurityPolicy, validate_http_client_policy, validate_http_url};
use crate::identity::{
    AgentIdentity, parse_agent_id, read_identity, verify_identity_document, write_identity,
};
use crate::key_provider::{
    IdentityKeyMaterial, KeyProvider, KeyProviderInfo, LocalKeyProvider, VaultKeyProvider,
};
use crate::messages::{
    AcpMessage, CompensateInstruction, DeliveryMode, DeliveryOutcome, DeliveryState, Envelope,
    MessageClass, SendResult, build_ack_payload, build_fail_payload,
};
use crate::mqtt_transport::MqttTransportClient;
use crate::options::AcpAgentOptions;
use crate::transport::{TransportClient, TransportResponse};
use crate::well_known::build_well_known_document;

#[derive(Debug, Clone, Serialize)]
pub struct InboundResult {
    pub state: DeliveryState,
    pub reason_code: Option<String>,
    pub detail: Option<String>,
    pub decrypted_payload: Option<Map<String, Value>>,
    pub response_message: Option<Map<String, Value>>,
}

#[derive(Debug, Clone)]
pub struct DecryptedMessage {
    pub message: AcpMessage,
    pub payload: Map<String, Value>,
}

pub type InboundHandlerFn =
    dyn for<'a> Fn(&'a Map<String, Value>, &'a Envelope) -> Option<Map<String, Value>>;

#[derive(Debug, Clone)]
pub struct CapabilityRequestResult {
    pub result: SendResult,
    pub capabilities: Option<Map<String, Value>>,
}

#[derive(Debug, Clone)]
pub struct AcpAgent {
    pub identity: AgentIdentity,
    pub identity_document: Map<String, Value>,
    pub discovery: DiscoveryClient,
    pub transport: TransportClient,
    pub amqp_transport: Option<AmqpTransportClient>,
    pub mqtt_transport: Option<MqttTransportClient>,
    pub capabilities: AgentCapabilities,
    pub storage_dir: PathBuf,
    pub trust_profile: String,
    pub relay_url: String,
    pub default_delivery_mode: DeliveryMode,
    pub key_provider_info: KeyProviderInfo,
    delivery_states: HashMap<String, HashMap<String, String>>,
    dedup: DedupStore,
}

impl AcpAgent {
    pub fn load_or_create(agent_id: &str, options: Option<AcpAgentOptions>) -> AcpResult<Self> {
        parse_agent_id(agent_id)?;
        let options = options.unwrap_or_default();
        std::fs::create_dir_all(&options.storage_dir)?;

        let key_provider = resolve_key_provider(&options)?;
        let key_provider_info = key_provider.describe();

        let provider_tls_material = key_provider.load_tls_material(agent_id).ok();
        let provider_ca_bundle = key_provider.load_ca_bundle(agent_id).ok().flatten();

        let effective_ca_file = first_non_blank(&[
            options.ca_file.clone(),
            provider_tls_material
                .as_ref()
                .and_then(|m| m.ca_file.clone()),
            provider_ca_bundle,
        ]);
        let effective_cert_file = first_non_blank(&[
            options.cert_file.clone(),
            provider_tls_material
                .as_ref()
                .and_then(|m| m.cert_file.clone()),
        ]);
        let effective_key_file = first_non_blank(&[
            options.key_file.clone(),
            provider_tls_material
                .as_ref()
                .and_then(|m| m.key_file.clone()),
        ]);

        let policy = HttpSecurityPolicy {
            allow_insecure_http: options.allow_insecure_http,
            allow_insecure_tls: options.allow_insecure_tls,
            mtls_enabled: options.mtls_enabled,
            ca_file: effective_ca_file.clone(),
            cert_file: effective_cert_file.clone(),
            key_file: effective_key_file.clone(),
        };
        validate_http_client_policy(&policy, "Agent HTTP security configuration")?;
        if let Some(endpoint) = options.endpoint.as_deref() {
            validate_http_url(
                endpoint,
                policy.allow_insecure_http,
                policy.mtls_enabled,
                "Agent direct endpoint configuration",
            )?;
        }
        validate_http_url(
            &options.relay_url,
            policy.allow_insecure_http,
            policy.mtls_enabled,
            "Agent relay URL configuration",
        )?;
        for relay_hint in &options.relay_hints {
            validate_http_url(
                relay_hint,
                policy.allow_insecure_http,
                policy.mtls_enabled,
                "Agent relay hint configuration",
            )?;
        }
        for directory_hint in &options.enterprise_directory_hints {
            validate_http_url(
                directory_hint,
                policy.allow_insecure_http,
                policy.mtls_enabled,
                "Agent enterprise directory hint configuration",
            )?;
        }

        let local_amqp_service = build_local_amqp_service(agent_id, &options)?;
        let local_mqtt_service = build_local_mqtt_service(agent_id, &options)?;

        let provider_identity_keys = key_provider.load_identity_keys(agent_id).ok();
        let external_key_provider = !matches_provider_local(&key_provider_info);

        let (identity, identity_document, capabilities) =
            match read_identity(&options.storage_dir, agent_id)? {
                None => {
                    let identity = if let Some(keys) = &provider_identity_keys {
                        identity_from_provider(agent_id, keys)?
                    } else if external_key_provider {
                        return Err(AcpError::KeyProvider(
                            "Unable to load identity keys from key provider".to_string(),
                        ));
                    } else {
                        AgentIdentity::create(agent_id)?
                    };
                    let capabilities = options
                        .capabilities
                        .clone()
                        .unwrap_or_else(|| AgentCapabilities::new(agent_id.to_string()));
                    let mut identity_document = identity.build_identity_document(
                        options.endpoint.as_deref(),
                        &options.relay_hints,
                        &options.trust_profile,
                        Some(&capabilities.to_map()),
                        365,
                        local_amqp_service.as_ref(),
                        local_mqtt_service.as_ref(),
                        if options.mtls_enabled {
                            Some("mtls")
                        } else {
                            None
                        },
                        if options.mtls_enabled {
                            Some("mtls")
                        } else {
                            None
                        },
                    )?;
                    apply_http_security_profile(&mut identity_document, options.mtls_enabled);
                    write_identity(&options.storage_dir, &identity, &identity_document)?;
                    (identity, identity_document, capabilities)
                }
                Some(bundle) => {
                    let mut identity = bundle.identity;
                    let mut identity_document = bundle.identity_document;
                    if let Some(keys) = &provider_identity_keys {
                        identity = apply_provider_keys(&identity, keys)?;
                    } else if external_key_provider {
                        return Err(AcpError::KeyProvider(
                            "Unable to load identity keys from key provider".to_string(),
                        ));
                    }
                    let valid_document = verify_identity_document(&identity_document);
                    let capabilities = options.capabilities.clone().unwrap_or_else(|| {
                        AgentCapabilities::from_map(
                            identity_document
                                .get("capabilities")
                                .and_then(Value::as_object),
                            agent_id,
                        )
                    });
                    let should_rewrite = !valid_document
                        || options.endpoint.is_some()
                        || !options.relay_hints.is_empty()
                        || options.capabilities.is_some()
                        || local_amqp_service.is_some()
                        || local_mqtt_service.is_some();
                    if should_rewrite {
                        let existing_service = identity_document
                            .get("service")
                            .and_then(Value::as_object)
                            .cloned()
                            .unwrap_or_default();
                        let existing_endpoint = existing_service
                            .get("direct_endpoint")
                            .and_then(Value::as_str)
                            .map(str::to_string);
                        let existing_hints = existing_service
                            .get("relay_hints")
                            .and_then(Value::as_array)
                            .map(|items| {
                                items
                                    .iter()
                                    .filter_map(Value::as_str)
                                    .map(str::to_string)
                                    .collect::<Vec<_>>()
                            })
                            .unwrap_or_default();
                        let existing_amqp_service = existing_service
                            .get("amqp")
                            .and_then(Value::as_object)
                            .cloned();
                        let existing_mqtt_service = existing_service
                            .get("mqtt")
                            .and_then(Value::as_object)
                            .cloned();
                        identity_document = identity.build_identity_document(
                            options.endpoint.as_deref().or(existing_endpoint.as_deref()),
                            if options.relay_hints.is_empty() {
                                &existing_hints
                            } else {
                                &options.relay_hints
                            },
                            &options.trust_profile,
                            Some(&capabilities.to_map()),
                            365,
                            local_amqp_service
                                .as_ref()
                                .or(existing_amqp_service.as_ref()),
                            local_mqtt_service
                                .as_ref()
                                .or(existing_mqtt_service.as_ref()),
                            if options.mtls_enabled {
                                Some("mtls")
                            } else {
                                None
                            },
                            if options.mtls_enabled {
                                Some("mtls")
                            } else {
                                None
                            },
                        )?;
                        apply_http_security_profile(&mut identity_document, options.mtls_enabled);
                        write_identity(&options.storage_dir, &identity, &identity_document)?;
                    }
                    (identity, identity_document, capabilities)
                }
            };

        let mut effective_relay_hints = if !options.relay_hints.is_empty() {
            options.relay_hints.clone()
        } else {
            identity_document
                .get("service")
                .and_then(Value::as_object)
                .and_then(|service| service.get("relay_hints"))
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::to_string)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default()
        };
        if !effective_relay_hints.contains(&options.relay_url) {
            effective_relay_hints.push(options.relay_url.clone());
        }

        let mut discovery = DiscoveryClient::new(
            Some(options.storage_dir.join("discovery_cache.json")),
            Some(options.discovery_scheme.clone()),
            Some(effective_relay_hints),
            Some(options.enterprise_directory_hints.clone()),
            options.http_timeout_seconds,
            policy.allow_insecure_http,
            policy.allow_insecure_tls,
            policy.ca_file.clone(),
            policy.mtls_enabled,
            policy.cert_file.clone(),
            policy.key_file.clone(),
        )?;
        discovery.seed(identity_document.clone())?;

        let amqp_transport = if let Some(transport) = options.amqp_transport.clone() {
            Some(transport)
        } else if let Some(broker_url) = options.amqp_broker_url.as_deref() {
            Some(AmqpTransportClient::new(
                broker_url.to_string(),
                Some(options.amqp_exchange.clone()),
                Some(options.amqp_exchange_type.clone()),
                options.http_timeout_seconds,
            )?)
        } else {
            None
        };

        let mqtt_transport = if let Some(transport) = options.mqtt_transport.clone() {
            Some(transport)
        } else if let Some(broker_url) = options.mqtt_broker_url.as_deref() {
            Some(MqttTransportClient::new(
                broker_url.to_string(),
                Some(options.mqtt_qos),
                Some(options.mqtt_topic_prefix.clone()),
                options.http_timeout_seconds,
                30,
            )?)
        } else {
            None
        };

        Ok(Self {
            identity,
            identity_document,
            discovery,
            transport: TransportClient::new(options.http_timeout_seconds, &policy)?,
            amqp_transport,
            mqtt_transport,
            capabilities,
            storage_dir: options.storage_dir,
            trust_profile: options.trust_profile,
            relay_url: options.relay_url,
            default_delivery_mode: options.default_delivery_mode,
            key_provider_info,
            delivery_states: HashMap::new(),
            dedup: DedupStore::new(Duration::from_secs(3600)),
        })
    }

    pub fn agent_id(&self) -> &str {
        &self.identity.agent_id
    }

    pub fn get_delivery_states(&self) -> &HashMap<String, HashMap<String, String>> {
        &self.delivery_states
    }

    pub fn build_well_known_document(
        &self,
        base_url: Option<&str>,
        identity_document_url: Option<&str>,
    ) -> AcpResult<Map<String, Value>> {
        let resolved_base_url = base_url
            .map(str::to_string)
            .or_else(|| {
                self.identity_document
                    .get("service")
                    .and_then(Value::as_object)
                    .and_then(|service| service.get("direct_endpoint"))
                    .and_then(Value::as_str)
                    .and_then(base_url_from_endpoint)
            })
            .ok_or_else(|| {
                AcpError::Validation(
                    "Unable to build /.well-known/acp metadata without base_url or direct_endpoint"
                        .to_string(),
                )
            })?;
        build_well_known_document(
            &self.identity_document,
            &resolved_base_url,
            identity_document_url,
            Some(ACP_VERSION),
        )
    }

    pub fn register_identity_document(
        &mut self,
        identity_document: Map<String, Value>,
    ) -> AcpResult<()> {
        self.discovery.register_identity_document(identity_document)
    }

    pub fn resolve_well_known(
        &mut self,
        base_url: &str,
        expected_agent_id: Option<&str>,
    ) -> AcpResult<Map<String, Value>> {
        self.discovery
            .resolve_well_known(base_url, expected_agent_id)
    }

    pub fn send(
        &mut self,
        recipients: Vec<String>,
        payload: Map<String, Value>,
        context: Option<String>,
        message_class: MessageClass,
        expires_in_seconds: i64,
        correlation_id: Option<String>,
        in_reply_to: Option<String>,
        delivery_mode: Option<DeliveryMode>,
    ) -> AcpResult<SendResult> {
        if recipients.is_empty() {
            return Err(AcpError::InvalidArgument(
                "send() requires at least one recipient".to_string(),
            ));
        }
        let mode = delivery_mode.unwrap_or(self.default_delivery_mode);
        let operation_id = Uuid::new_v4().to_string();
        let context_id = context.unwrap_or_else(|| operation_id.clone());

        let resolved = self.resolve_recipients(&recipients, mode)?;
        if resolved.deliverable.is_empty() {
            let result = SendResult {
                operation_id: operation_id.clone(),
                message_id: Uuid::new_v4().to_string(),
                message_ids: Vec::new(),
                outcomes: resolved.preflight_outcomes.clone(),
            };
            self.sync_delivery_states(&operation_id, &result.outcomes);
            return Ok(result);
        }

        let mut outcomes = resolved.preflight_outcomes;
        let mut message_ids = Vec::new();
        let direct_targets = resolved
            .deliverable
            .iter()
            .filter(|target| target.channel == "direct")
            .cloned()
            .collect::<Vec<_>>();
        let relay_targets = resolved
            .deliverable
            .iter()
            .filter(|target| target.channel == "relay")
            .cloned()
            .collect::<Vec<_>>();
        let amqp_targets = resolved
            .deliverable
            .iter()
            .filter(|target| target.channel == "amqp")
            .cloned()
            .collect::<Vec<_>>();
        let mqtt_targets = resolved
            .deliverable
            .iter()
            .filter(|target| target.channel == "mqtt")
            .cloned()
            .collect::<Vec<_>>();

        if !direct_targets.is_empty() {
            let message = self.build_message(
                direct_targets.iter().map(|r| r.recipient.clone()).collect(),
                &payload,
                &to_public_key_map(&direct_targets),
                message_class,
                &context_id,
                Some(operation_id.clone()),
                expires_in_seconds,
                correlation_id.clone(),
                in_reply_to.clone(),
            )?;
            message_ids.push(message.envelope.message_id.clone());
            outcomes.extend(self.deliver_direct(&message, &direct_targets));
        }
        if !relay_targets.is_empty() {
            let message = self.build_message(
                relay_targets.iter().map(|r| r.recipient.clone()).collect(),
                &payload,
                &to_public_key_map(&relay_targets),
                message_class,
                &context_id,
                Some(operation_id.clone()),
                expires_in_seconds,
                correlation_id.clone(),
                in_reply_to.clone(),
            )?;
            message_ids.push(message.envelope.message_id.clone());
            outcomes.extend(self.deliver_via_relay(&message, &relay_targets));
        }
        for target in &amqp_targets {
            let recipient_public_keys =
                HashMap::from([(target.recipient.clone(), target.public_key.clone())]);
            let message = self.build_message(
                vec![target.recipient.clone()],
                &payload,
                &recipient_public_keys,
                message_class,
                &context_id,
                Some(operation_id.clone()),
                expires_in_seconds,
                correlation_id.clone(),
                in_reply_to.clone(),
            )?;
            message_ids.push(message.envelope.message_id.clone());
            outcomes.push(self.deliver_via_amqp(&message, target));
        }
        for target in &mqtt_targets {
            let recipient_public_keys =
                HashMap::from([(target.recipient.clone(), target.public_key.clone())]);
            let message = self.build_message(
                vec![target.recipient.clone()],
                &payload,
                &recipient_public_keys,
                message_class,
                &context_id,
                Some(operation_id.clone()),
                expires_in_seconds,
                correlation_id.clone(),
                in_reply_to.clone(),
            )?;
            message_ids.push(message.envelope.message_id.clone());
            outcomes.push(self.deliver_via_mqtt(&message, target));
        }
        if message_ids.is_empty() {
            message_ids.push(Uuid::new_v4().to_string());
        }
        let result = SendResult {
            operation_id: operation_id.clone(),
            message_id: message_ids[0].clone(),
            message_ids,
            outcomes,
        };
        self.sync_delivery_states(&operation_id, &result.outcomes);
        Ok(result)
    }

    pub fn send_basic(
        &mut self,
        recipients: Vec<String>,
        payload: Map<String, Value>,
        context: Option<String>,
    ) -> AcpResult<SendResult> {
        self.send(
            recipients,
            payload,
            context,
            MessageClass::Send,
            300,
            None,
            None,
            Some(self.default_delivery_mode),
        )
    }

    pub fn send_compensate(
        &mut self,
        recipients: Vec<String>,
        original_operation_id: &str,
        reason: &str,
        actions: Vec<Map<String, Value>>,
        context: Option<String>,
        delivery_mode: Option<DeliveryMode>,
    ) -> AcpResult<SendResult> {
        let instruction = CompensateInstruction {
            operation_id: original_operation_id.to_string(),
            reason: reason.to_string(),
            actions,
        };
        let mut payload = Map::new();
        payload.insert(
            "compensation".to_string(),
            serde_json::to_value(instruction).unwrap_or(Value::Null),
        );
        self.send(
            recipients,
            payload,
            context.or_else(|| Some(format!("compensate:{original_operation_id}"))),
            MessageClass::Compensate,
            300,
            Some(original_operation_id.to_string()),
            None,
            delivery_mode,
        )
    }

    pub fn decrypt_message_for_self(
        &mut self,
        raw_message: &Map<String, Value>,
    ) -> AcpResult<DecryptedMessage> {
        let message = AcpMessage::from_map(raw_message)?;
        self.validate_envelope_for_inbound(&message.envelope)?;
        if !message
            .envelope
            .recipients
            .iter()
            .any(|recipient| recipient == self.agent_id())
        {
            return Err(AcpError::Processing {
                reason: FailReason::PolicyRejected,
                detail: "Message is not addressed to this agent".to_string(),
            });
        }
        let sender_doc =
            self.resolve_sender_identity_document(raw_message, &message.envelope.sender)?;
        let sender_signing_key = sender_doc
            .get("keys")
            .and_then(Value::as_object)
            .and_then(|keys| keys.get("signing"))
            .and_then(Value::as_object)
            .and_then(|signing| signing.get("public_key"))
            .and_then(Value::as_str)
            .ok_or_else(|| AcpError::Processing {
                reason: FailReason::InvalidSignature,
                detail: "Sender signing public key missing".to_string(),
            })?;
        if !crypto::verify_protected_payload_signature(
            &message.envelope,
            &message.protected_payload,
            sender_signing_key,
        ) {
            return Err(AcpError::Processing {
                reason: FailReason::InvalidSignature,
                detail: "Message signature verification failed".to_string(),
            });
        }
        let payload = crypto::decrypt_for_recipient(
            &message.envelope,
            &message.protected_payload,
            self.agent_id(),
            &self.identity.encryption_private_key,
        )?;
        Ok(DecryptedMessage { message, payload })
    }

    pub fn receive(
        &mut self,
        raw_message: &Map<String, Value>,
        handler: Option<&InboundHandlerFn>,
    ) -> InboundResult {
        let mut result = InboundResult {
            state: DeliveryState::Failed,
            reason_code: None,
            detail: None,
            decrypted_payload: None,
            response_message: None,
        };

        let request_message = match AcpMessage::from_map(raw_message) {
            Ok(message) => message,
            Err(exc) => {
                result.reason_code = Some(FailReason::PolicyRejected.as_str().to_string());
                result.detail = Some(format!("Invalid ACP message structure: {exc}"));
                return result;
            }
        };

        let mut sender_identity_document: Option<Map<String, Value>> = None;

        let processing_result = (|| -> AcpResult<()> {
            self.validate_envelope_for_inbound(&request_message.envelope)?;
            if !request_message
                .envelope
                .recipients
                .iter()
                .any(|recipient| recipient == self.agent_id())
            {
                return Err(AcpError::Processing {
                    reason: FailReason::PolicyRejected,
                    detail: format!("Recipient {} not in message recipients", self.agent_id()),
                });
            }

            let sender_doc = self
                .resolve_sender_identity_document(raw_message, &request_message.envelope.sender)?;
            sender_identity_document = Some(sender_doc.clone());
            let sender_signing_key = sender_doc
                .get("keys")
                .and_then(Value::as_object)
                .and_then(|keys| keys.get("signing"))
                .and_then(Value::as_object)
                .and_then(|signing| signing.get("public_key"))
                .and_then(Value::as_str)
                .ok_or_else(|| AcpError::Processing {
                    reason: FailReason::InvalidSignature,
                    detail: "Sender signing key missing from identity document".to_string(),
                })?;
            if !crypto::verify_protected_payload_signature(
                &request_message.envelope,
                &request_message.protected_payload,
                sender_signing_key,
            ) {
                return Err(AcpError::Processing {
                    reason: FailReason::InvalidSignature,
                    detail: "Signature verification failed".to_string(),
                });
            }

            if self
                .dedup
                .is_duplicate(&request_message.envelope.message_id)
            {
                result.state = DeliveryState::Acknowledged;
                result.detail = Some("Duplicate message acknowledged".to_string());
                if !matches!(
                    request_message.envelope.message_class,
                    MessageClass::Ack | MessageClass::Fail
                ) {
                    let duplicate_ack = self.create_response_message(
                        &sender_doc,
                        &request_message.envelope,
                        MessageClass::Ack,
                        build_ack_payload(&request_message.envelope.message_id, "duplicate"),
                    )?;
                    result.response_message = Some(duplicate_ack.to_map()?);
                }
                return Ok(());
            }

            let decrypted_payload = crypto::decrypt_for_recipient(
                &request_message.envelope,
                &request_message.protected_payload,
                self.agent_id(),
                &self.identity.encryption_private_key,
            )?;
            result.decrypted_payload = Some(decrypted_payload.clone());

            let response_message =
                if request_message.envelope.message_class == MessageClass::Capabilities {
                    Some(self.create_response_message(
                        &sender_doc,
                        &request_message.envelope,
                        MessageClass::Capabilities,
                        self.capabilities.to_map(),
                    )?)
                } else {
                    let mut ack_payload =
                        build_ack_payload(&request_message.envelope.message_id, "accepted");
                    if let Some(handler) = handler
                        && let Some(handler_payload) =
                            handler(&decrypted_payload, &request_message.envelope)
                        && !handler_payload.is_empty()
                    {
                        ack_payload.insert("handler".to_string(), Value::Object(handler_payload));
                    }
                    if matches!(
                        request_message.envelope.message_class,
                        MessageClass::Ack | MessageClass::Fail
                    ) {
                        None
                    } else {
                        Some(self.create_response_message(
                            &sender_doc,
                            &request_message.envelope,
                            MessageClass::Ack,
                            ack_payload,
                        )?)
                    }
                };

            self.dedup
                .mark_processed(&request_message.envelope.message_id);
            result.state = DeliveryState::Acknowledged;
            result.response_message = response_message
                .map(|message| message.to_map())
                .transpose()?;
            Ok(())
        })();

        if let Err(exc) = processing_result {
            let (reason_code, detail) = match exc {
                AcpError::Processing { reason, detail } => (reason.as_str().to_string(), detail),
                _ => (
                    FailReason::PolicyRejected.as_str().to_string(),
                    exc.to_string(),
                ),
            };
            result.reason_code = Some(reason_code.clone());
            result.detail = Some(detail.clone());
            if let Some(sender_doc) = sender_identity_document {
                let fail_response = self.create_response_message(
                    &sender_doc,
                    &request_message.envelope,
                    MessageClass::Fail,
                    build_fail_payload(reason_code, detail, false),
                );
                result.response_message =
                    fail_response.ok().and_then(|message| message.to_map().ok());
            }
        }
        result
    }

    pub fn request_capabilities(&mut self, recipient: &str) -> AcpResult<CapabilityRequestResult> {
        let mut payload = Map::new();
        payload.insert(
            "request".to_string(),
            Value::String("capabilities".to_string()),
        );
        let result = self.send(
            vec![recipient.to_string()],
            payload,
            Some(format!("capabilities:{}", Uuid::new_v4())),
            MessageClass::Capabilities,
            300,
            None,
            None,
            Some(self.default_delivery_mode),
        )?;
        let mut response_payload = None;
        for outcome in &result.outcomes {
            let Some(response_message) = &outcome.response_message else {
                continue;
            };
            if let Ok(decrypted) = self.decrypt_message_for_self(response_message)
                && decrypted.message.envelope.message_class == MessageClass::Capabilities
            {
                response_payload = Some(decrypted.payload);
                break;
            }
        }
        Ok(CapabilityRequestResult {
            result,
            capabilities: response_payload,
        })
    }

    pub fn consume_from_amqp<F>(
        &mut self,
        max_messages: usize,
        handler: Option<F>,
    ) -> AcpResult<usize>
    where
        F: Fn(&Map<String, Value>, &Envelope) -> Option<Map<String, Value>> + Send + 'static,
    {
        let amqp_transport = self.amqp_transport.clone().ok_or_else(|| {
            AcpError::Transport("consume_from_amqp requires an AMQP-configured agent".to_string())
        })?;
        let amqp_service = self
            .identity_document
            .get("service")
            .and_then(Value::as_object)
            .and_then(|service| service.get("amqp"))
            .and_then(Value::as_object)
            .cloned()
            .ok_or_else(|| {
                AcpError::Transport(
                    "Identity document is missing service.amqp configuration".to_string(),
                )
            })?;
        let agent_ptr = Arc::new(std::sync::Mutex::new(self.clone()));
        let agent_for_handler = Arc::clone(&agent_ptr);
        let processed = amqp_transport.consume(
            self.agent_id(),
            move |raw_message| {
                let Ok(mut guard) = agent_for_handler.lock() else {
                    return false;
                };
                let inbound = guard.receive(
                    raw_message,
                    handler.as_ref().map(|inner| inner as &InboundHandlerFn),
                );
                if let Some(response_message) = inbound.response_message.clone() {
                    if guard
                        .publish_amqp_response_message(raw_message, &response_message)
                        .is_err()
                    {
                        return false;
                    }
                }
                matches!(
                    inbound.state,
                    DeliveryState::Acknowledged
                        | DeliveryState::Failed
                        | DeliveryState::Declined
                        | DeliveryState::Expired
                )
            },
            Some(&amqp_service),
            max_messages,
        )?;
        if let Ok(guard) = agent_ptr.lock() {
            *self = guard.clone();
        }
        Ok(processed)
    }

    pub fn consume_from_mqtt<F>(
        &mut self,
        max_messages: usize,
        handler: Option<F>,
    ) -> AcpResult<usize>
    where
        F: Fn(&Map<String, Value>, &Envelope) -> Option<Map<String, Value>> + Send + 'static,
    {
        let mqtt_transport = self.mqtt_transport.clone().ok_or_else(|| {
            AcpError::Transport("consume_from_mqtt requires an MQTT-configured agent".to_string())
        })?;
        let mqtt_service = self
            .identity_document
            .get("service")
            .and_then(Value::as_object)
            .and_then(|service| service.get("mqtt"))
            .and_then(Value::as_object)
            .cloned()
            .ok_or_else(|| {
                AcpError::Transport(
                    "Identity document is missing service.mqtt configuration".to_string(),
                )
            })?;
        let agent_ptr = Arc::new(std::sync::Mutex::new(self.clone()));
        let agent_for_handler = Arc::clone(&agent_ptr);
        let processed = mqtt_transport.consume(
            self.agent_id(),
            move |raw_message| {
                let Ok(mut guard) = agent_for_handler.lock() else {
                    return false;
                };
                let inbound = guard.receive(
                    raw_message,
                    handler.as_ref().map(|inner| inner as &InboundHandlerFn),
                );
                if let Some(response_message) = inbound.response_message.clone() {
                    if guard
                        .publish_mqtt_response_message(raw_message, &response_message)
                        .is_err()
                    {
                        return false;
                    }
                }
                matches!(
                    inbound.state,
                    DeliveryState::Acknowledged
                        | DeliveryState::Failed
                        | DeliveryState::Declined
                        | DeliveryState::Expired
                )
            },
            Some(&mqtt_service),
            max_messages,
            Duration::from_secs(1),
        )?;
        if let Ok(guard) = agent_ptr.lock() {
            *self = guard.clone();
        }
        Ok(processed)
    }

    fn resolve_recipients(
        &mut self,
        recipients: &[String],
        mode: DeliveryMode,
    ) -> AcpResult<ResolvedRecipients> {
        let mut deliverable = Vec::new();
        let mut preflight_outcomes = Vec::new();
        for recipient in recipients {
            let identity_doc = match self.discovery.resolve(recipient) {
                Ok(identity_doc) => identity_doc,
                Err(exc) => {
                    preflight_outcomes.push(failed_outcome(
                        recipient,
                        FailReason::PolicyRejected.as_str(),
                        &exc.to_string(),
                    ));
                    continue;
                }
            };
            let remote_capabilities = AgentCapabilities::from_map(
                identity_doc.get("capabilities").and_then(Value::as_object),
                recipient,
            );
            let capability_match = self.capabilities.choose_compatible(&remote_capabilities);
            if !capability_match.compatible {
                preflight_outcomes.push(failed_outcome(
                    recipient,
                    reason_for_capability_mismatch(capability_match.reason.as_deref()).as_str(),
                    capability_match
                        .reason
                        .as_deref()
                        .unwrap_or("No compatible capabilities"),
                ));
                continue;
            }
            let choice = self.choose_delivery_channel(&remote_capabilities, &identity_doc, mode)?;
            let Some(channel) = choice.channel else {
                preflight_outcomes.push(failed_outcome(
                    recipient,
                    FailReason::PolicyRejected.as_str(),
                    choice
                        .detail
                        .as_deref()
                        .unwrap_or("Delivery channel unavailable"),
                ));
                continue;
            };
            let recipient_public_key = identity_doc
                .get("keys")
                .and_then(Value::as_object)
                .and_then(|keys| keys.get("encryption"))
                .and_then(Value::as_object)
                .and_then(|enc| enc.get("public_key"))
                .and_then(Value::as_str)
                .map(str::to_string);
            let Some(recipient_public_key) = recipient_public_key else {
                preflight_outcomes.push(failed_outcome(
                    recipient,
                    FailReason::PolicyRejected.as_str(),
                    "Recipient identity document missing encryption public key",
                ));
                continue;
            };
            deliverable.push(ResolvedRecipient {
                recipient: recipient.to_string(),
                public_key: recipient_public_key,
                channel,
                endpoint: choice.endpoint,
                amqp_service: choice.amqp_service,
                mqtt_service: choice.mqtt_service,
            });
        }
        Ok(ResolvedRecipients {
            deliverable,
            preflight_outcomes,
        })
    }

    fn choose_delivery_channel(
        &self,
        remote_capabilities: &AgentCapabilities,
        identity_document: &Map<String, Value>,
        mode: DeliveryMode,
    ) -> AcpResult<ChannelChoice> {
        let remote_transports: HashSet<String> = remote_capabilities
            .transports
            .iter()
            .map(|t| t.to_lowercase())
            .collect();
        let shared = self
            .capabilities
            .transports
            .iter()
            .filter(|transport| remote_transports.contains(&transport.to_lowercase()))
            .map(|transport| transport.to_lowercase())
            .collect::<Vec<_>>();

        let service = identity_document
            .get("service")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let direct_endpoint = service
            .get("direct_endpoint")
            .and_then(Value::as_str)
            .map(str::to_string);
        let has_direct = direct_endpoint
            .as_deref()
            .map(|endpoint| !endpoint.trim().is_empty())
            .unwrap_or(false);
        let direct_available = has_direct
            && shared
                .iter()
                .any(|transport| matches!(transport.as_str(), "https" | "http" | "direct"));
        let relay_available =
            !self.relay_url.trim().is_empty() && shared.iter().any(|t| t == "relay");
        let amqp_service = service.get("amqp").and_then(Value::as_object).cloned();
        let amqp_available = shared.iter().any(|t| t == "amqp")
            && amqp_service
                .as_ref()
                .and_then(|service| service.get("broker_url"))
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .is_some();
        let mqtt_service = service.get("mqtt").and_then(Value::as_object).cloned();
        let mqtt_available = shared.iter().any(|t| t == "mqtt")
            && mqtt_service
                .as_ref()
                .and_then(|service| service.get("broker_url"))
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .is_some()
            && mqtt_service
                .as_ref()
                .and_then(|service| service.get("topic"))
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .is_some();

        match mode {
            DeliveryMode::Direct => {
                if direct_available {
                    return Ok(ChannelChoice::new(
                        Some("direct".to_string()),
                        direct_endpoint,
                        None,
                        None,
                        None,
                    ));
                }
                return Ok(ChannelChoice::new(
                    None,
                    None,
                    None,
                    None,
                    Some("No compatible direct transport and endpoint available".to_string()),
                ));
            }
            DeliveryMode::Relay => {
                if relay_available {
                    return Ok(ChannelChoice::new(
                        Some("relay".to_string()),
                        None,
                        None,
                        None,
                        None,
                    ));
                }
                return Ok(ChannelChoice::new(
                    None,
                    None,
                    None,
                    None,
                    Some("No compatible relay transport available".to_string()),
                ));
            }
            DeliveryMode::Amqp => {
                if amqp_available {
                    return Ok(ChannelChoice::new(
                        Some("amqp".to_string()),
                        None,
                        amqp_service,
                        None,
                        None,
                    ));
                }
                return Ok(ChannelChoice::new(
                    None,
                    None,
                    None,
                    None,
                    Some("No compatible AMQP transport available".to_string()),
                ));
            }
            DeliveryMode::Mqtt => {
                if mqtt_available {
                    return Ok(ChannelChoice::new(
                        Some("mqtt".to_string()),
                        None,
                        None,
                        mqtt_service,
                        None,
                    ));
                }
                return Ok(ChannelChoice::new(
                    None,
                    None,
                    None,
                    None,
                    Some("No compatible MQTT transport available".to_string()),
                ));
            }
            DeliveryMode::Auto => {}
        }

        if direct_available {
            return Ok(ChannelChoice::new(
                Some("direct".to_string()),
                direct_endpoint,
                None,
                None,
                None,
            ));
        }
        if relay_available {
            return Ok(ChannelChoice::new(
                Some("relay".to_string()),
                None,
                None,
                None,
                None,
            ));
        }
        if amqp_available {
            return Ok(ChannelChoice::new(
                Some("amqp".to_string()),
                None,
                amqp_service,
                None,
                None,
            ));
        }
        if mqtt_available {
            return Ok(ChannelChoice::new(
                Some("mqtt".to_string()),
                None,
                None,
                mqtt_service,
                None,
            ));
        }
        if has_direct {
            return Ok(ChannelChoice::new(
                None,
                None,
                None,
                None,
                Some(
                    "No compatible transport implementation available for this recipient"
                        .to_string(),
                ),
            ));
        }
        if amqp_service.is_some() {
            return Ok(ChannelChoice::new(
                None,
                None,
                None,
                None,
                Some(
                    "AMQP transport is advertised but not compatible with sender capabilities"
                        .to_string(),
                ),
            ));
        }
        if mqtt_service.is_some() {
            return Ok(ChannelChoice::new(
                None,
                None,
                None,
                None,
                Some(
                    "MQTT transport is advertised but not compatible with sender capabilities"
                        .to_string(),
                ),
            ));
        }
        Ok(ChannelChoice::new(
            None,
            None,
            None,
            None,
            Some(
                "Recipient identity document is missing direct_endpoint/amqp/mqtt and no relay fallback is compatible"
                    .to_string(),
            ),
        ))
    }

    #[allow(clippy::too_many_arguments)]
    fn build_message(
        &self,
        recipients: Vec<String>,
        payload: &Map<String, Value>,
        recipient_public_keys: &HashMap<String, String>,
        message_class: MessageClass,
        context_id: &str,
        operation_id: Option<String>,
        expires_in_seconds: i64,
        correlation_id: Option<String>,
        in_reply_to: Option<String>,
    ) -> AcpResult<AcpMessage> {
        let envelope = Envelope::build(
            self.agent_id().to_string(),
            recipients,
            message_class,
            context_id.to_string(),
            expires_in_seconds,
            operation_id,
            correlation_id,
            in_reply_to,
            Some(DEFAULT_CRYPTO_SUITE.to_string()),
        )?;
        let mut protected_payload =
            crypto::encrypt_for_recipients(payload, &envelope, recipient_public_keys)?;
        crypto::sign_protected_payload(
            &envelope,
            &mut protected_payload,
            &self.identity.signing_private_key,
            &self.identity.signing_kid,
        )?;
        Ok(AcpMessage {
            envelope,
            protected_payload,
            sender_identity_document: Some(self.identity_document.clone()),
        })
    }

    fn deliver_direct(
        &self,
        message: &AcpMessage,
        targets: &[ResolvedRecipient],
    ) -> Vec<DeliveryOutcome> {
        let mut outcomes = Vec::new();
        let message_map = match message.to_map() {
            Ok(map) => map,
            Err(exc) => {
                for target in targets {
                    outcomes.push(failed_outcome(
                        &target.recipient,
                        FailReason::PolicyRejected.as_str(),
                        &format!("Message serialization failure: {exc}"),
                    ));
                }
                return outcomes;
            }
        };
        for target in targets {
            let Some(endpoint) = target.endpoint.as_deref() else {
                outcomes.push(failed_outcome(
                    &target.recipient,
                    FailReason::PolicyRejected.as_str(),
                    "Missing direct endpoint for direct delivery",
                ));
                continue;
            };
            match self.transport.post_json(endpoint, &message_map) {
                Ok(response) => {
                    outcomes.push(outcome_from_http_response(&target.recipient, &response))
                }
                Err(exc) => outcomes.push(failed_outcome(
                    &target.recipient,
                    FailReason::PolicyRejected.as_str(),
                    &format!("Direct transport failure: {exc}"),
                )),
            }
        }
        outcomes
    }

    fn deliver_via_relay(
        &self,
        message: &AcpMessage,
        targets: &[ResolvedRecipient],
    ) -> Vec<DeliveryOutcome> {
        let mut outcomes = Vec::new();
        match self.transport.send_to_relay(&self.relay_url, message) {
            Ok(relay_response) => {
                let mut delivered = HashSet::new();
                if let Some(raw_outcomes) = relay_response.get("outcomes").and_then(Value::as_array)
                {
                    for item in raw_outcomes {
                        if let Ok(outcome) = serde_json::from_value::<DeliveryOutcome>(item.clone())
                        {
                            delivered.insert(outcome.recipient.clone());
                            outcomes.push(outcome);
                        }
                    }
                }
                for target in targets {
                    if !delivered.contains(&target.recipient) {
                        outcomes.push(failed_outcome(
                            &target.recipient,
                            FailReason::PolicyRejected.as_str(),
                            "Relay did not return an outcome for recipient",
                        ));
                    }
                }
            }
            Err(exc) => {
                for target in targets {
                    outcomes.push(failed_outcome(
                        &target.recipient,
                        FailReason::PolicyRejected.as_str(),
                        &format!("Relay transport failure: {exc}"),
                    ));
                }
            }
        }
        outcomes
    }

    fn deliver_via_amqp(
        &self,
        message: &AcpMessage,
        target: &ResolvedRecipient,
    ) -> DeliveryOutcome {
        let mut outcome = DeliveryOutcome {
            recipient: target.recipient.clone(),
            state: DeliveryState::Pending,
            status_code: None,
            response_class: None,
            reason_code: None,
            detail: None,
            response_message: None,
        };
        let message_map = match message.to_map() {
            Ok(message_map) => message_map,
            Err(exc) => {
                outcome.state = DeliveryState::Failed;
                outcome.reason_code = Some(FailReason::PolicyRejected.as_str().to_string());
                outcome.detail = Some(format!("AMQP message serialization failure: {exc}"));
                return outcome;
            }
        };
        let result = (|| -> AcpResult<()> {
            let client = if let Some(amqp_transport) = &self.amqp_transport {
                amqp_transport.clone()
            } else {
                let broker_url = target
                    .amqp_service
                    .as_ref()
                    .and_then(|service| service.get("broker_url"))
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        AcpError::Transport(
                            "AMQP delivery selected but sender is not configured with an AMQP broker"
                                .to_string(),
                        )
                    })?;
                AmqpTransportClient::new(
                    broker_url.to_string(),
                    target
                        .amqp_service
                        .as_ref()
                        .and_then(|service| service.get("exchange"))
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    None,
                    10,
                )?
            };
            client.publish(
                &message_map,
                &target.recipient,
                target.amqp_service.as_ref(),
            )
        })();
        match result {
            Ok(()) => outcome.state = DeliveryState::Delivered,
            Err(exc) => {
                outcome.state = DeliveryState::Failed;
                outcome.reason_code = Some(FailReason::PolicyRejected.as_str().to_string());
                outcome.detail = Some(format!("AMQP transport failure: {exc}"));
            }
        }
        outcome
    }

    fn deliver_via_mqtt(
        &self,
        message: &AcpMessage,
        target: &ResolvedRecipient,
    ) -> DeliveryOutcome {
        let mut outcome = DeliveryOutcome {
            recipient: target.recipient.clone(),
            state: DeliveryState::Pending,
            status_code: None,
            response_class: None,
            reason_code: None,
            detail: None,
            response_message: None,
        };
        let message_map = match message.to_map() {
            Ok(message_map) => message_map,
            Err(exc) => {
                outcome.state = DeliveryState::Failed;
                outcome.reason_code = Some(FailReason::PolicyRejected.as_str().to_string());
                outcome.detail = Some(format!("MQTT message serialization failure: {exc}"));
                return outcome;
            }
        };
        let result = (|| -> AcpResult<()> {
            let client = if let Some(mqtt_transport) = &self.mqtt_transport {
                mqtt_transport.clone()
            } else {
                let service = target.mqtt_service.as_ref().ok_or_else(|| {
                    AcpError::Transport(
                        "MQTT delivery selected but sender is not configured with an MQTT broker"
                            .to_string(),
                    )
                })?;
                let broker_url = service
                    .get("broker_url")
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        AcpError::Transport(
                            "MQTT delivery selected but sender is not configured with an MQTT broker"
                                .to_string(),
                        )
                    })?;
                MqttTransportClient::new(
                    broker_url.to_string(),
                    service.get("qos").and_then(|v| v.as_u64()).map(|v| v as u8),
                    None,
                    10,
                    30,
                )?
            };
            client.publish(
                &message_map,
                &target.recipient,
                target.mqtt_service.as_ref(),
            )
        })();
        match result {
            Ok(()) => outcome.state = DeliveryState::Delivered,
            Err(exc) => {
                outcome.state = DeliveryState::Failed;
                outcome.reason_code = Some(FailReason::PolicyRejected.as_str().to_string());
                outcome.detail = Some(format!("MQTT transport failure: {exc}"));
            }
        }
        outcome
    }

    fn publish_amqp_response_message(
        &mut self,
        raw_message: &Map<String, Value>,
        response_message: &Map<String, Value>,
    ) -> AcpResult<()> {
        let amqp_transport = self
            .amqp_transport
            .clone()
            .ok_or_else(|| AcpError::Transport("AMQP transport is not configured".to_string()))?;
        let sender_id = raw_message
            .get("envelope")
            .and_then(Value::as_object)
            .and_then(|envelope| envelope.get("sender"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                AcpError::Transport(
                    "Inbound message sender is missing for AMQP response routing".to_string(),
                )
            })?;
        let sender_identity = self.resolve_sender_identity_document(raw_message, sender_id)?;
        let sender_amqp_service = sender_identity
            .get("service")
            .and_then(Value::as_object)
            .and_then(|service| service.get("amqp"))
            .and_then(Value::as_object)
            .cloned()
            .ok_or_else(|| {
                AcpError::Transport(format!(
                    "Sender {sender_id} does not advertise service.amqp for AMQP response delivery"
                ))
            })?;
        amqp_transport.publish(response_message, sender_id, Some(&sender_amqp_service))
    }

    fn publish_mqtt_response_message(
        &mut self,
        raw_message: &Map<String, Value>,
        response_message: &Map<String, Value>,
    ) -> AcpResult<()> {
        let mqtt_transport = self
            .mqtt_transport
            .clone()
            .ok_or_else(|| AcpError::Transport("MQTT transport is not configured".to_string()))?;
        let sender_id = raw_message
            .get("envelope")
            .and_then(Value::as_object)
            .and_then(|envelope| envelope.get("sender"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                AcpError::Transport(
                    "Inbound message sender is missing for MQTT response routing".to_string(),
                )
            })?;
        let sender_identity = self.resolve_sender_identity_document(raw_message, sender_id)?;
        let sender_mqtt_service = sender_identity
            .get("service")
            .and_then(Value::as_object)
            .and_then(|service| service.get("mqtt"))
            .and_then(Value::as_object)
            .cloned()
            .ok_or_else(|| {
                AcpError::Transport(format!(
                    "Sender {sender_id} does not advertise service.mqtt for MQTT response delivery"
                ))
            })?;
        mqtt_transport.publish(response_message, sender_id, Some(&sender_mqtt_service))
    }

    fn resolve_sender_identity_document(
        &mut self,
        raw_message: &Map<String, Value>,
        sender_id: &str,
    ) -> AcpResult<Map<String, Value>> {
        if let Some(embedded) = raw_message
            .get("sender_identity_document")
            .and_then(Value::as_object)
            .cloned()
            && embedded.get("agent_id").and_then(Value::as_str) == Some(sender_id)
            && verify_identity_document(&embedded)
        {
            // Cache verified embedded identity documents to avoid blocking discovery lookups
            // when replying to the same sender in the current request cycle.
            let _ = self.discovery.register_identity_document(embedded.clone());
            return Ok(embedded);
        }
        self.discovery.resolve(sender_id)
    }

    fn validate_envelope_for_inbound(&self, envelope: &Envelope) -> AcpResult<()> {
        if envelope.acp_version != ACP_VERSION {
            return Err(AcpError::Processing {
                reason: FailReason::UnsupportedVersion,
                detail: format!("Unsupported ACP version: {}", envelope.acp_version),
            });
        }
        if envelope.crypto_suite != DEFAULT_CRYPTO_SUITE {
            return Err(AcpError::Processing {
                reason: FailReason::UnsupportedCryptoSuite,
                detail: format!("Unsupported crypto suite: {}", envelope.crypto_suite),
            });
        }
        if envelope.is_expired() {
            return Err(AcpError::Processing {
                reason: FailReason::ExpiredMessage,
                detail: "Message is expired".to_string(),
            });
        }
        Ok(())
    }

    fn create_response_message(
        &self,
        sender_identity_document: &Map<String, Value>,
        request_envelope: &Envelope,
        response_class: MessageClass,
        response_payload: Map<String, Value>,
    ) -> AcpResult<AcpMessage> {
        let sender_id = &request_envelope.sender;
        let sender_encryption_public_key = sender_identity_document
            .get("keys")
            .and_then(Value::as_object)
            .and_then(|keys| keys.get("encryption"))
            .and_then(Value::as_object)
            .and_then(|encryption| encryption.get("public_key"))
            .and_then(Value::as_str)
            .ok_or_else(|| AcpError::Processing {
                reason: FailReason::PolicyRejected,
                detail: "Sender identity document missing encryption key".to_string(),
            })?;
        self.build_message(
            vec![sender_id.to_string()],
            &response_payload,
            &HashMap::from([(
                sender_id.to_string(),
                sender_encryption_public_key.to_string(),
            )]),
            response_class,
            &request_envelope.context_id,
            Some(request_envelope.operation_id.clone()),
            300,
            request_envelope
                .correlation_id
                .clone()
                .or_else(|| Some(request_envelope.operation_id.clone())),
            Some(request_envelope.message_id.clone()),
        )
    }

    fn sync_delivery_states(&mut self, operation_id: &str, outcomes: &[DeliveryOutcome]) {
        let mut states = HashMap::new();
        for outcome in outcomes {
            states.insert(
                outcome.recipient.clone(),
                format!("{:?}", outcome.state).to_uppercase(),
            );
        }
        self.delivery_states
            .insert(operation_id.to_string(), states);
    }
}

#[derive(Debug, Clone)]
struct ResolvedRecipient {
    recipient: String,
    public_key: String,
    channel: String,
    endpoint: Option<String>,
    amqp_service: Option<Map<String, Value>>,
    mqtt_service: Option<Map<String, Value>>,
}

#[derive(Debug, Clone)]
struct ResolvedRecipients {
    deliverable: Vec<ResolvedRecipient>,
    preflight_outcomes: Vec<DeliveryOutcome>,
}

#[derive(Debug, Clone)]
struct ChannelChoice {
    channel: Option<String>,
    endpoint: Option<String>,
    amqp_service: Option<Map<String, Value>>,
    mqtt_service: Option<Map<String, Value>>,
    detail: Option<String>,
}

impl ChannelChoice {
    fn new(
        channel: Option<String>,
        endpoint: Option<String>,
        amqp_service: Option<Map<String, Value>>,
        mqtt_service: Option<Map<String, Value>>,
        detail: Option<String>,
    ) -> Self {
        Self {
            channel,
            endpoint,
            amqp_service,
            mqtt_service,
            detail,
        }
    }
}

#[derive(Debug, Clone)]
struct DedupStore {
    ttl: Duration,
    processed: HashMap<String, Instant>,
}

impl DedupStore {
    fn new(ttl: Duration) -> Self {
        Self {
            ttl,
            processed: HashMap::new(),
        }
    }

    fn is_duplicate(&mut self, message_id: &str) -> bool {
        self.cleanup_expired();
        self.processed.contains_key(message_id)
    }

    fn mark_processed(&mut self, message_id: &str) {
        self.processed
            .insert(message_id.to_string(), Instant::now());
    }

    fn cleanup_expired(&mut self) {
        let ttl = self.ttl;
        self.processed
            .retain(|_, timestamp| timestamp.elapsed() < ttl);
    }
}

fn outcome_from_http_response(recipient: &str, response: &TransportResponse) -> DeliveryOutcome {
    let mut response_class = None;
    let mut response_message = None;
    let mut reason_code = None;
    let mut detail = None;

    if let Some(body) = &response.body {
        if let Some(raw_response_message) = body.get("response_message").and_then(Value::as_object)
        {
            response_message = Some(raw_response_message.clone());
            response_class = raw_response_message
                .get("envelope")
                .and_then(Value::as_object)
                .and_then(|envelope| envelope.get("message_class"))
                .and_then(Value::as_str)
                .and_then(parse_message_class);
        }
        reason_code = body
            .get("reason_code")
            .and_then(Value::as_str)
            .map(str::to_string);
        detail = body
            .get("detail")
            .and_then(Value::as_str)
            .map(str::to_string);
    }
    if detail.is_none() && response.status_code >= 400 {
        detail = Some(format!("Recipient HTTP {}", response.status_code));
    }

    DeliveryOutcome {
        recipient: recipient.to_string(),
        state: delivery_state_from_response(
            response.status_code,
            response_class,
            reason_code.as_deref(),
        ),
        status_code: Some(response.status_code),
        response_class,
        reason_code,
        detail,
        response_message,
    }
}

fn delivery_state_from_response(
    status_code: u16,
    response_class: Option<MessageClass>,
    reason_code: Option<&str>,
) -> DeliveryState {
    if (200..300).contains(&status_code) {
        if response_class == Some(MessageClass::Fail) {
            if reason_code == Some(FailReason::ExpiredMessage.as_str()) {
                return DeliveryState::Expired;
            }
            if reason_code == Some(FailReason::PolicyRejected.as_str()) {
                return DeliveryState::Declined;
            }
            return DeliveryState::Failed;
        }
        if matches!(
            response_class,
            Some(MessageClass::Ack | MessageClass::Capabilities)
        ) {
            return DeliveryState::Acknowledged;
        }
        return DeliveryState::Delivered;
    }
    if status_code == 410 {
        return DeliveryState::Expired;
    }
    if [401, 403, 409, 422].contains(&status_code) {
        return DeliveryState::Declined;
    }
    DeliveryState::Failed
}

fn parse_message_class(value: &str) -> Option<MessageClass> {
    match value {
        "SEND" => Some(MessageClass::Send),
        "ACK" => Some(MessageClass::Ack),
        "FAIL" => Some(MessageClass::Fail),
        "CAPABILITIES" => Some(MessageClass::Capabilities),
        "COMPENSATE" => Some(MessageClass::Compensate),
        _ => None,
    }
}

fn failed_outcome(recipient: &str, reason_code: &str, detail: &str) -> DeliveryOutcome {
    DeliveryOutcome {
        recipient: recipient.to_string(),
        state: DeliveryState::Failed,
        status_code: None,
        response_class: None,
        reason_code: Some(reason_code.to_string()),
        detail: Some(detail.to_string()),
        response_message: None,
    }
}

fn to_public_key_map(targets: &[ResolvedRecipient]) -> HashMap<String, String> {
    targets
        .iter()
        .map(|target| (target.recipient.clone(), target.public_key.clone()))
        .collect()
}

fn reason_for_capability_mismatch(reason: Option<&str>) -> FailReason {
    let normalized = reason.unwrap_or_default().to_lowercase();
    if normalized.contains("protocol") {
        return FailReason::UnsupportedVersion;
    }
    if normalized.contains("crypto") {
        return FailReason::UnsupportedCryptoSuite;
    }
    if normalized.contains("profile") {
        return FailReason::UnsupportedProfile;
    }
    FailReason::PolicyRejected
}

fn build_local_amqp_service(
    agent_id: &str,
    options: &AcpAgentOptions,
) -> AcpResult<Option<Map<String, Value>>> {
    let Some(broker_url) = options.amqp_broker_url.as_deref() else {
        return Ok(None);
    };
    Ok(Some(AmqpTransportClient::build_service_hint(
        agent_id,
        broker_url,
        Some(&options.amqp_exchange),
    )?))
}

fn build_local_mqtt_service(
    agent_id: &str,
    options: &AcpAgentOptions,
) -> AcpResult<Option<Map<String, Value>>> {
    let Some(broker_url) = options.mqtt_broker_url.as_deref() else {
        return Ok(None);
    };
    Ok(Some(MqttTransportClient::build_service_hint(
        agent_id,
        broker_url,
        None,
        Some(options.mqtt_qos),
        Some(&options.mqtt_topic_prefix),
    )?))
}

fn apply_http_security_profile(identity_document: &mut Map<String, Value>, mtls_enabled: bool) {
    if !mtls_enabled {
        return;
    }
    let mut service = identity_document
        .get("service")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let direct_endpoint = service
        .get("direct_endpoint")
        .and_then(Value::as_str)
        .map(str::to_string);
    let relay_hints = service
        .get("relay_hints")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if let Some(endpoint) = direct_endpoint
        && !endpoint.trim().is_empty()
    {
        service.insert(
            "http".to_string(),
            serde_json::json!({
                "endpoint": endpoint,
                "security_profile": "mtls",
            }),
        );
    }
    if let Some(relay_endpoint) = relay_hints.first()
        && !relay_endpoint.trim().is_empty()
    {
        service.insert(
            "relay".to_string(),
            serde_json::json!({
                "endpoint": relay_endpoint,
                "security_profile": "mtls",
            }),
        );
    }
    identity_document.insert("service".to_string(), Value::Object(service));
}

fn resolve_key_provider(options: &AcpAgentOptions) -> AcpResult<Box<dyn KeyProvider>> {
    if let Some(provider) = options.key_provider_instance.clone() {
        return Ok(Box::new(ArcKeyProvider(provider)));
    }
    let provider_name = normalize_key_provider_name(&options.key_provider);
    match provider_name.as_str() {
        "local" => Ok(Box::new(LocalKeyProvider::new(
            options.storage_dir.clone(),
            options.cert_file.clone(),
            options.key_file.clone(),
            options.ca_file.clone(),
        ))),
        "vault" => {
            let vault_url = options.vault_url.clone().ok_or_else(|| {
                AcpError::Validation("vault_url is required when key_provider=vault".to_string())
            })?;
            let vault_path = options.vault_path.clone().ok_or_else(|| {
                AcpError::Validation("vault_path is required when key_provider=vault".to_string())
            })?;
            Ok(Box::new(VaultKeyProvider::new(
                vault_url,
                vault_path,
                Some(options.vault_token_env.clone()),
                options.vault_token.clone(),
                options.http_timeout_seconds,
                options.ca_file.clone(),
                options.allow_insecure_tls,
                options.allow_insecure_http,
            )?))
        }
        _ => Err(AcpError::Validation(format!(
            "Unsupported key_provider: {}",
            options.key_provider
        ))),
    }
}

fn normalize_key_provider_name(value: &str) -> String {
    let normalized = value.trim().to_lowercase();
    if normalized.is_empty() {
        "local".to_string()
    } else {
        normalized
    }
}

fn matches_provider_local(key_provider_info: &KeyProviderInfo) -> bool {
    key_provider_info
        .get("provider")
        .and_then(Value::as_str)
        .map(|provider| provider == "local")
        .unwrap_or(false)
}

fn identity_from_provider(agent_id: &str, keys: &IdentityKeyMaterial) -> AcpResult<AgentIdentity> {
    let mut missing = Vec::new();
    if keys
        .signing_public_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .is_none()
    {
        missing.push("signing_public_key");
    }
    if keys
        .encryption_public_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .is_none()
    {
        missing.push("encryption_public_key");
    }
    if keys
        .signing_kid
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .is_none()
    {
        missing.push("signing_kid");
    }
    if keys
        .encryption_kid
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .is_none()
    {
        missing.push("encryption_kid");
    }
    if !missing.is_empty() {
        return Err(AcpError::Validation(format!(
            "External key provider requires identity public metadata for first-time bootstrap: {}",
            missing.join(", ")
        )));
    }
    Ok(AgentIdentity {
        agent_id: agent_id.to_string(),
        signing_private_key: keys.signing_private_key.clone(),
        signing_public_key: keys.signing_public_key.clone().unwrap_or_default(),
        encryption_private_key: keys.encryption_private_key.clone(),
        encryption_public_key: keys.encryption_public_key.clone().unwrap_or_default(),
        signing_kid: keys.signing_kid.clone().unwrap_or_default(),
        encryption_kid: keys.encryption_kid.clone().unwrap_or_default(),
    })
}

fn apply_provider_keys(
    identity: &AgentIdentity,
    keys: &IdentityKeyMaterial,
) -> AcpResult<AgentIdentity> {
    if let Some(signing_public_key) = keys.signing_public_key.as_deref()
        && signing_public_key != identity.signing_public_key
    {
        return Err(AcpError::Validation(
            "Key provider signing_public_key does not match local identity metadata".to_string(),
        ));
    }
    if let Some(encryption_public_key) = keys.encryption_public_key.as_deref()
        && encryption_public_key != identity.encryption_public_key
    {
        return Err(AcpError::Validation(
            "Key provider encryption_public_key does not match local identity metadata".to_string(),
        ));
    }
    if let Some(signing_kid) = keys.signing_kid.as_deref()
        && signing_kid != identity.signing_kid
    {
        return Err(AcpError::Validation(
            "Key provider signing_kid does not match local identity metadata".to_string(),
        ));
    }
    if let Some(encryption_kid) = keys.encryption_kid.as_deref()
        && encryption_kid != identity.encryption_kid
    {
        return Err(AcpError::Validation(
            "Key provider encryption_kid does not match local identity metadata".to_string(),
        ));
    }
    Ok(AgentIdentity {
        agent_id: identity.agent_id.clone(),
        signing_private_key: keys.signing_private_key.clone(),
        signing_public_key: identity.signing_public_key.clone(),
        encryption_private_key: keys.encryption_private_key.clone(),
        encryption_public_key: identity.encryption_public_key.clone(),
        signing_kid: identity.signing_kid.clone(),
        encryption_kid: identity.encryption_kid.clone(),
    })
}

fn base_url_from_endpoint(endpoint: &str) -> Option<String> {
    let endpoint = endpoint.trim();
    if endpoint.is_empty() {
        return None;
    }
    let parsed = url::Url::parse(endpoint).ok()?;
    let scheme = parsed.scheme();
    let host = parsed.host_str()?;
    let authority = if let Some(port) = parsed.port() {
        format!("{host}:{port}")
    } else {
        host.to_string()
    };
    Some(format!("{scheme}://{authority}"))
}

fn first_non_blank(values: &[Option<String>]) -> Option<String> {
    values
        .iter()
        .flatten()
        .map(|value| value.trim())
        .find(|value| !value.is_empty())
        .map(str::to_string)
}

#[derive(Clone)]
struct ArcKeyProvider(Arc<dyn KeyProvider>);

impl KeyProvider for ArcKeyProvider {
    fn load_identity_keys(&self, agent_id: &str) -> AcpResult<IdentityKeyMaterial> {
        self.0.load_identity_keys(agent_id)
    }

    fn load_tls_material(&self, agent_id: &str) -> AcpResult<crate::key_provider::TlsMaterial> {
        self.0.load_tls_material(agent_id)
    }

    fn load_ca_bundle(&self, agent_id: &str) -> AcpResult<Option<String>> {
        self.0.load_ca_bundle(agent_id)
    }

    fn describe(&self) -> KeyProviderInfo {
        self.0.describe()
    }
}
