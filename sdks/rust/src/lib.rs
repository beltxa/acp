//! # ACP — Agent Communication Protocol
//!
//! ACP (Agent Communication Protocol) is a secure, identity-driven protocol
//! for autonomous systems to communicate, discover each other, and collaborate
//! across environments.
//!
//! Unlike traditional APIs or message brokers, ACP is designed for
//! **agent-to-agent communication** with:
//!
//! - identity-based addressing
//! - signed and verifiable messages
//! - transport independence (HTTP, AMQP, MQTT)
//! - optional relay-based routing
//!
//! ---
//!
//! ## What this crate provides
//!
//! This crate is the **Rust runtime for ACP**, allowing you to:
//!
//! - create and manage agent identities
//! - send and receive ACP messages
//! - integrate with relays and transports
//! - build autonomous systems using a consistent protocol
//!
//! ---
//!
//! ## Quick example
//!
//! ```rust
//! use acp_runtime::AcpAgent;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let agent = AcpAgent::load_or_create("agent:demo", None)?;
//!
//! agent.send("agent:other", "ping", serde_json::json!({
//!     "message": "hello"
//! }))?;
//!
//! # Ok(())
//! # }
//! ```
//! ---
//! ## Interoperability
//!
//! ACP agents written in different languages (Python, TypeScript, Rust, Java)
//! can communicate seamlessly using the same protocol semantics.
//! ---
//!
//! ## Mental model
//!
//! - HTTP is for services
//! - ACP is for agents
//!
//! ---
//!
//! ## More information
//!
//! - GitHub: https://github.com/beltxa/acp
//! - Protocol overview: see repository README
//!
//! ---

// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

pub mod agent;
pub mod amqp_transport;
pub mod capabilities;
pub mod constants;
pub mod crypto;
pub mod discovery;
pub mod errors;
pub mod http_security;
pub mod identity;
pub mod json_support;
pub mod key_provider;
pub mod messages;
pub mod mqtt_transport;
pub mod options;
pub mod overlay;
pub mod overlay_framework;
pub mod transport;
pub mod well_known;

pub use agent::{AcpAgent, CapabilityRequestResult, DecryptedMessage, InboundResult};
pub use amqp_transport::{
    AmqpMessageHandler, AmqpTransportClient, DEFAULT_AMQP_EXCHANGE, DEFAULT_AMQP_EXCHANGE_TYPE,
};
pub use capabilities::{AgentCapabilities, CapabilityMatch};
pub use constants::{ACP_IDENTITY_VERSION, ACP_VERSION, DEFAULT_CRYPTO_SUITE, TRUST_PROFILES};
pub use discovery::DiscoveryClient;
pub use errors::{AcpError, AcpResult, FailReason};
pub use identity::{AgentIdParts, AgentIdentity, IdentityBundle};
pub use key_provider::{
    IdentityKeyMaterial, KeyProvider, KeyProviderInfo, LocalKeyProvider, TlsMaterial,
    VaultKeyProvider,
};
pub use messages::{
    AcpMessage, CompensateInstruction, DeliveryMode, DeliveryOutcome, DeliveryState, Envelope,
    MessageClass, ProtectedPayload, SendResult, WrappedContentKey,
};
pub use mqtt_transport::{
    DEFAULT_MQTT_QOS, DEFAULT_MQTT_TOPIC_PREFIX, MqttMessageHandler, MqttTransportClient,
};
pub use options::AcpAgentOptions;
pub use overlay::{
    OverlayInboundAdapter, OverlayOutboundAdapter, OverlaySendResult, OverlayTarget,
};
pub use overlay_framework::{
    OverlayClient, OverlayConfig, OverlayFrameworkRuntime, OverlayHttpResponse,
    WELL_KNOWN_CACHE_CONTROL,
};
