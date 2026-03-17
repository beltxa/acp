use std::fs;
use std::path::{Path, PathBuf};

use acp::well_known::parse_well_known_document;
use serde_json::Value;

fn vectors_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("tests")
        .join("vectors")
        .join("well_known")
}

#[test]
fn well_known_valid_fixture_parses() {
    let value = load_json_fixture("valid_basic.json");
    let parsed = parse_well_known_document(&value).expect("valid fixture should parse");
    assert_eq!(
        Some("agent:shipping.bot@company.local"),
        parsed.get("agent_id").and_then(Value::as_str)
    );
}

#[test]
fn well_known_invalid_fixtures_fail_validation() {
    for fixture in [
        "invalid_missing_agent_id.json",
        "invalid_missing_version.json",
        "invalid_identity_document_type.json",
        "invalid_identity_document_relative_path.json",
        "invalid_identity_document_url.json",
        "invalid_transports_type.json",
        "invalid_transport_hint_shape.json",
        "invalid_transport_endpoint_type.json",
        "invalid_transport_endpoint_url.json",
        "invalid_version.json",
        "invalid_security_profile.json",
    ] {
        let value = load_json_fixture(fixture);
        assert!(
            parse_well_known_document(&value).is_err(),
            "fixture {fixture} must fail validation"
        );
    }
}

#[test]
fn malformed_json_fixture_fails_parse() {
    let path = vectors_dir().join("malformed_json.txt");
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("unable to read fixture {}: {err}", path.display()));
    assert!(
        serde_json::from_str::<Value>(&raw).is_err(),
        "malformed fixture must be invalid JSON"
    );
}

fn load_json_fixture(name: &str) -> Value {
    let path = vectors_dir().join(name);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("unable to read fixture {}: {err}", path.display()));
    serde_json::from_str::<Value>(&raw)
        .unwrap_or_else(|err| panic!("unable to parse fixture {}: {err}", path.display()))
}
