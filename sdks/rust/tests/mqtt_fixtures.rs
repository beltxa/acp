use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use acp::messages::AcpMessage;
use acp::mqtt_transport::MqttTransportClient;
use serde_json::{Map, Value};

fn vectors_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("tests")
        .join("vectors")
        .join("mqtt")
}

const REQUIRED_FIXTURES: &[&str] = &[
    "python_to_python_send.json",
    "java_to_python_send.json",
    "python_to_java_send.json",
    "multi_recipient_send_B.json",
    "multi_recipient_send_C.json",
    "multi_recipient_send_D.json",
    "duplicate_delivery_case.json",
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
fn required_mqtt_fixture_files_exist() {
    let vectors_dir = vectors_dir();
    for fixture in REQUIRED_FIXTURES {
        assert!(
            vectors_dir.join(fixture).is_file(),
            "missing required fixture: {fixture}"
        );
    }
}

#[test]
fn standard_fixtures_match_topic_and_metadata_conventions() {
    for fixture in STANDARD_FIXTURES {
        let fixture_map = load_fixture(fixture);
        let body = as_object(
            fixture_map.get("serialized_body"),
            "serialized_body must be an object",
        )
        .clone();
        AcpMessage::from_map(&body).expect("fixture serialized_body must parse as ACP message");

        let envelope = as_object(body.get("envelope"), "envelope must be object");
        let recipients = as_array(envelope.get("recipients"), "recipients must be array");
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
        assert_eq!(
            MqttTransportClient::topic_for_agent(recipient, None)
                .expect("topic derivation should succeed"),
            as_string(transport.get("topic"), "topic must be string")
        );
        assert_eq!(1, as_u64(transport.get("qos"), "qos must be number"));
        assert_eq!(
            metadata_properties(&body),
            *as_object(
                transport.get("user_properties"),
                "user_properties must be object"
            )
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

fn load_fixture(name: &str) -> Map<String, Value> {
    let path = vectors_dir().join(name);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("unable to read fixture {}: {err}", path.display()));
    serde_json::from_str::<Map<String, Value>>(&raw)
        .unwrap_or_else(|err| panic!("unable to parse fixture {}: {err}", path.display()))
}

fn metadata_properties(body: &Map<String, Value>) -> Map<String, Value> {
    let envelope = as_object(body.get("envelope"), "envelope must be object");
    let mut properties: HashMap<String, String> = HashMap::new();
    for (source_key, metadata_key) in [
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
            properties.insert(metadata_key.to_string(), value.to_string());
        }
    }
    properties
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

fn as_u64(value: Option<&Value>, message: &str) -> u64 {
    value.and_then(Value::as_u64).expect(message)
}
