use std::collections::BTreeMap;

use acp_runtime::AcpAgent;
use acp_runtime::messages::DeliveryMode;
use acp_runtime::options::AcpAgentOptions;
use acp_runtime::overlay_framework::OverlayClient;
use serde_json::{Map, Value};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let from_agent_id = env_string(
        "ACP_FROM_AGENT_ID",
        "agent:overlay.rust.sender@localhost:9031".to_string(),
    );
    let target_base_url = env_string("ACP_TARGET_BASE_URL", "http://localhost:9010".to_string());
    let storage_dir = env_string(
        "ACP_STORAGE_DIR",
        ".acp-data-overlay-rust-sender".to_string(),
    );
    let allow_insecure_http = env_bool("ACP_ALLOW_INSECURE_HTTP", true);
    let recipient_agent_id = std::env::var("ACP_RECIPIENT_AGENT_ID").ok();
    let context = env_string("ACP_CONTEXT", "overlay:rust:client".to_string());
    let payload = payload_from_env()?;

    let discovery_scheme = if target_base_url.starts_with("http://") {
        "http".to_string()
    } else {
        "https".to_string()
    };
    let options = AcpAgentOptions {
        storage_dir: storage_dir.into(),
        allow_insecure_http,
        discovery_scheme,
        ..AcpAgentOptions::default()
    };
    let agent = AcpAgent::load_or_create(&from_agent_id, Some(options))?;
    let mut client = OverlayClient::create(agent);
    let result = client.send_acp(
        &target_base_url,
        payload,
        recipient_agent_id.as_deref(),
        Some(context),
        Some(DeliveryMode::Auto),
        120,
    )?;
    println!("{}", serde_json::to_string_pretty(&Value::Object(result))?);
    Ok(())
}

fn payload_from_env() -> Result<Map<String, Value>, Box<dyn std::error::Error>> {
    if let Ok(raw) = std::env::var("ACP_PAYLOAD_JSON") {
        let value: Value = serde_json::from_str(&raw)?;
        let object = value
            .as_object()
            .ok_or("ACP_PAYLOAD_JSON must be a JSON object")?
            .clone();
        return Ok(object);
    }
    let mut default_payload = Map::new();
    default_payload.insert(
        "kind".to_string(),
        Value::String("rust-overlay-client".to_string()),
    );
    default_payload.insert(
        "attributes".to_string(),
        Value::Object(
            BTreeMap::from([
                (
                    "source".to_string(),
                    Value::String("acp example".to_string()),
                ),
                ("mode".to_string(), Value::String("overlay".to_string())),
            ])
            .into_iter()
            .collect(),
        ),
    );
    Ok(default_payload)
}

fn env_string(key: &str, default_value: String) -> String {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or(default_value)
}

fn env_bool(key: &str, default_value: bool) -> bool {
    std::env::var(key)
        .ok()
        .map(|value| match value.trim().to_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => default_value,
        })
        .unwrap_or(default_value)
}
