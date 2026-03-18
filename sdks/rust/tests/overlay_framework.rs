use std::sync::Arc;

use acp_runtime::agent::AcpAgent;
use acp_runtime::messages::DeliveryMode;
use acp_runtime::options::AcpAgentOptions;
use acp_runtime::overlay_framework::{OverlayClient, OverlayFrameworkRuntime};
use httpmock::prelude::*;
use serde_json::{Map, Value};

#[test]
fn overlay_runtime_exposes_well_known_headers_and_rejects_non_object_body() {
    let temp = tempfile::tempdir().expect("tempdir");
    let agent = AcpAgent::load_or_create(
        "agent:overlay.runtime@localhost:9541",
        Some(AcpAgentOptions {
            storage_dir: temp.path().join("runtime-agent"),
            endpoint: Some("http://localhost:9541/acp/inbox".to_string()),
            allow_insecure_http: true,
            discovery_scheme: "http".to_string(),
            ..AcpAgentOptions::default()
        }),
    )
    .expect("runtime agent");
    let mut runtime = OverlayFrameworkRuntime::create(
        agent,
        "http://localhost:9541",
        Arc::new(|payload| {
            let mut response = Map::new();
            response.insert("accepted".to_string(), Value::Bool(true));
            response.insert("echo".to_string(), Value::Object(payload.clone()));
            Some(response)
        }),
        None,
    )
    .expect("overlay runtime");

    let headers = OverlayFrameworkRuntime::well_known_headers();
    assert_eq!(
        Some("public, max-age=300"),
        headers.get("Cache-Control").and_then(Value::as_str)
    );
    let well_known = runtime
        .well_known_document()
        .expect("well-known document should be built");
    assert_eq!(
        Some("agent:overlay.runtime@localhost:9541"),
        well_known.get("agent_id").and_then(Value::as_str)
    );
    assert_eq!(
        Some("1.0"),
        well_known.get("version").and_then(Value::as_str)
    );

    let invalid_response =
        runtime.handle_message_body(&Value::Array(vec![Value::String("invalid".to_string())]));
    assert_eq!(400, invalid_response.status_code);
    assert_eq!(
        Some("FAILED"),
        invalid_response.body.get("state").and_then(Value::as_str)
    );
    assert_eq!(
        Some("POLICY_REJECTED"),
        invalid_response
            .body
            .get("reason_code")
            .and_then(Value::as_str)
    );
}

#[test]
fn overlay_client_bootstraps_well_known_and_sends_payload() {
    let server = MockServer::start();
    let base_url = format!("http://127.0.0.1:{}", server.port());

    let temp = tempfile::tempdir().expect("tempdir");
    let receiver = AcpAgent::load_or_create(
        "agent:overlay.receiver@localhost:9542",
        Some(AcpAgentOptions {
            storage_dir: temp.path().join("receiver"),
            endpoint: Some(format!("{base_url}/acp/inbox")),
            allow_insecure_http: true,
            discovery_scheme: "http".to_string(),
            ..AcpAgentOptions::default()
        }),
    )
    .expect("receiver agent");
    let well_known = receiver
        .build_well_known_document(Some(&base_url), None)
        .expect("receiver well-known");
    let mut identity_payload = Map::new();
    identity_payload.insert(
        "identity_document".to_string(),
        Value::Object(receiver.identity_document.clone()),
    );

    let well_known_mock = server.mock(|when, then| {
        when.method(GET).path("/.well-known/acp");
        then.status(200)
            .header("Content-Type", "application/json")
            .body(
                serde_json::to_string(&Value::Object(well_known.clone()))
                    .expect("serialize well-known"),
            );
    });
    let identity_mock = server.mock(|when, then| {
        when.method(GET).path("/api/v1/acp/identity");
        then.status(200)
            .header("Content-Type", "application/json")
            .body(
                serde_json::to_string(&Value::Object(identity_payload.clone()))
                    .expect("serialize identity payload"),
            );
    });
    let inbox_mock = server.mock(|when, then| {
        when.method(POST).path("/acp/inbox");
        then.status(200)
            .header("Content-Type", "application/json")
            .body("{\"status\":\"accepted\"}");
    });

    let sender = AcpAgent::load_or_create(
        "agent:overlay.sender@localhost:9543",
        Some(AcpAgentOptions {
            storage_dir: temp.path().join("sender"),
            allow_insecure_http: true,
            discovery_scheme: "http".to_string(),
            ..AcpAgentOptions::default()
        }),
    )
    .expect("sender agent");
    let mut client = OverlayClient::create(sender);
    let mut payload = Map::new();
    payload.insert(
        "kind".to_string(),
        Value::String("overlay-rust-test".to_string()),
    );

    let response = client
        .send_acp(
            &base_url,
            payload,
            None,
            Some("overlay:rust:outbound".to_string()),
            Some(DeliveryMode::Auto),
            120,
        )
        .expect("overlay outbound send");
    let target = response
        .get("target")
        .and_then(Value::as_object)
        .expect("target should be present");
    assert_eq!(
        Some("agent:overlay.receiver@localhost:9542"),
        target.get("agent_id").and_then(Value::as_str)
    );
    assert_eq!(
        Some(format!("{base_url}/.well-known/acp").as_str()),
        target.get("well_known_url").and_then(Value::as_str)
    );
    let outcomes = response
        .get("send_result")
        .and_then(Value::as_object)
        .and_then(|send_result| send_result.get("outcomes"))
        .and_then(Value::as_array)
        .expect("outcomes should be present");
    assert_eq!(1, outcomes.len());
    let state = outcomes[0]
        .get("state")
        .and_then(Value::as_str)
        .expect("delivery state should be present");
    assert!(
        matches!(state, "DELIVERED" | "ACKNOWLEDGED"),
        "unexpected delivery state: {state}"
    );

    well_known_mock.assert();
    identity_mock.assert();
    inbox_mock.assert();
}
