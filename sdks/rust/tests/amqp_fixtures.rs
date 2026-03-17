use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use acp::amqp_transport::AmqpTransportClient;
use acp::messages::AcpMessage;
use serde_json::{Map, Value};

fn vectors_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("tests")
        .join("vectors")
        .join("amqp")
}

const REQUIRED_FIXTURES: &[&str] = &[
    "python_to_python_send.json",
    "java_to_python_send.json",
    "python_to_java_send.json",
    "multi_recipient_send_B.json",
    "multi_recipient_send_C.json",
    "multi_recipient_send_D.json",
    "duplicate_delivery_case.json",
    "relay_amqp_fallback_case.json",
    "ack_example.json",
    "fail_example.json",
];

const STANDARD_FIXTURES: &[&str] = &[
    "python_to_python_send.json",
    "java_to_python_send.json",
    "python_to_java_send.json",
    "multi_recipient_send_B.json",
    "multi_recipient_send_C.json",
    "multi_recipient_send_D.json",
    "ack_example.json",
    "fail_example.json",
];

#[test]
fn required_amqp_fixture_files_exist() {
    let vectors_dir = vectors_dir();
    for fixture in REQUIRED_FIXTURES {
        assert!(
            vectors_dir.join(fixture).is_file(),
            "missing required fixture: {fixture}"
        );
    }
}

#[test]
fn standard_fixtures_match_routing_and_header_conventions() {
    for fixture in STANDARD_FIXTURES {
        let fixture_map = load_fixture(fixture);
        let body = as_object(
            fixture_map.get("serialized_body"),
            "serialized_body must be an object",
        )
        .clone();
        AcpMessage::from_map(&body).expect("fixture serialized_body must parse as ACP message");

        let envelope = as_object(body.get("envelope"), "envelope must be an object");
        let recipients = as_array(envelope.get("recipients"), "recipients must be an array");
        assert_eq!(
            1,
            recipients.len(),
            "fixture {fixture} must be single-recipient"
        );
        let recipient = as_string(recipients.first(), "recipient must be string");

        let transport = as_object(
            fixture_map.get("transport_metadata"),
            "transport_metadata must be an object",
        );
        let headers = as_object(transport.get("headers"), "headers must be an object");
        assert_eq!(metadata_headers(&body), *headers);
        assert_eq!(
            AmqpTransportClient::routing_key_for_agent(recipient)
                .expect("routing key derivation should succeed"),
            as_string(transport.get("routing_key"), "routing_key must be string")
        );
        assert_eq!(
            AmqpTransportClient::queue_name_for_agent(recipient)
                .expect("queue derivation should succeed"),
            as_string(transport.get("queue"), "queue must be string")
        );
    }
}

#[test]
fn duplicate_fixture_uses_same_message_id() {
    let fixture = load_fixture("duplicate_delivery_case.json");
    let original = as_object(
        fixture.get("original_message"),
        "original_message must be object",
    );
    let duplicate = as_object(
        fixture.get("duplicate_message"),
        "duplicate_message must be object",
    );
    let original_body = as_object(
        original.get("serialized_body"),
        "original serialized_body must be object",
    )
    .clone();
    let duplicate_body = as_object(
        duplicate.get("serialized_body"),
        "duplicate serialized_body must be object",
    )
    .clone();

    AcpMessage::from_map(&original_body).expect("original message should parse");
    AcpMessage::from_map(&duplicate_body).expect("duplicate message should parse");

    let original_envelope = as_object(
        original_body.get("envelope"),
        "original envelope must be object",
    );
    let duplicate_envelope = as_object(
        duplicate_body.get("envelope"),
        "duplicate envelope must be object",
    );
    assert_eq!(
        as_string(
            original_envelope.get("message_id"),
            "message_id must be string"
        ),
        as_string(
            duplicate_envelope.get("message_id"),
            "message_id must be string"
        )
    );
}

#[test]
fn relay_fallback_fixture_preserves_serialized_body() {
    let fixture = load_fixture("relay_amqp_fallback_case.json");
    let input = as_object(
        fixture.get("input_acp_message"),
        "input_acp_message must be object",
    );
    let emitted = as_object(
        fixture.get("emitted_amqp_message"),
        "emitted_amqp_message must be object",
    );
    let input_body = as_object(
        input.get("serialized_body"),
        "input serialized_body must be object",
    )
    .clone();
    let emitted_body = as_object(
        emitted.get("serialized_body"),
        "emitted serialized_body must be object",
    )
    .clone();

    AcpMessage::from_map(&input_body).expect("input message should parse");
    AcpMessage::from_map(&emitted_body).expect("emitted message should parse");
    assert_eq!(Value::Object(input_body), Value::Object(emitted_body));
}

fn load_fixture(name: &str) -> Map<String, Value> {
    let path = vectors_dir().join(name);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("unable to read fixture {}: {err}", path.display()));
    serde_json::from_str::<Map<String, Value>>(&raw)
        .unwrap_or_else(|err| panic!("unable to parse fixture {}: {err}", path.display()))
}

fn metadata_headers(body: &Map<String, Value>) -> Map<String, Value> {
    let envelope = as_object(body.get("envelope"), "envelope must be object");
    let mut headers: HashMap<String, String> = HashMap::new();
    for (source_key, header_key) in [
        ("acp_version", "acp_version"),
        ("message_class", "acp_message_class"),
        ("message_id", "acp_message_id"),
        ("operation_id", "acp_operation_id"),
        ("sender", "acp_sender"),
    ] {
        if let Some(value) = envelope
            .get(source_key)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            headers.insert(header_key.to_string(), value.to_string());
        }
    }
    headers
        .into_iter()
        .map(|(key, value)| (key, Value::String(value)))
        .collect()
}

fn as_object<'a>(value: Option<&'a Value>, message: &str) -> &'a Map<String, Value> {
    value.and_then(Value::as_object).expect(message)
}

fn as_array<'a>(value: Option<&'a Value>, message: &str) -> &'a Vec<Value> {
    value.and_then(Value::as_array).expect(message)
}

fn as_string<'a>(value: Option<&'a Value>, message: &str) -> &'a str {
    value.and_then(Value::as_str).expect(message)
}
