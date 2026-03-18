use acp_runtime::identity::AgentIdentity;
use acp_runtime::well_known::{build_well_known_document, parse_well_known_document};
use serde_json::Value;

#[test]
fn parse_well_known_accepts_valid_document() {
    let identity = AgentIdentity::create("agent:wellknown@demo").expect("identity");
    let identity_document = identity
        .build_identity_document(
            Some("https://agent.demo.example/messages"),
            &["https://relay.demo.example".to_string()],
            "self_asserted",
            None,
            365,
            None,
            None,
            Some("https"),
            Some("https"),
        )
        .expect("identity document");
    let well_known =
        build_well_known_document(&identity_document, "https://agent.demo.example", None, None)
            .expect("well-known document");

    let parsed = parse_well_known_document(&Value::Object(well_known.clone()))
        .expect("well-known should parse");
    assert_eq!(
        parsed.get("agent_id").and_then(Value::as_str),
        Some("agent:wellknown@demo")
    );
    assert_eq!(
        parsed.get("version").and_then(Value::as_str),
        Some(acp_runtime::constants::ACP_VERSION)
    );
}

#[test]
fn parse_well_known_rejects_missing_version() {
    let identity = AgentIdentity::create("agent:noversion@demo").expect("identity");
    let identity_document = identity
        .build_identity_document(
            Some("https://agent.demo.example/messages"),
            &[],
            "self_asserted",
            None,
            365,
            None,
            None,
            Some("https"),
            None,
        )
        .expect("identity document");
    let mut well_known =
        build_well_known_document(&identity_document, "https://agent.demo.example", None, None)
            .expect("well-known document");
    well_known.remove("version");

    assert!(
        parse_well_known_document(&Value::Object(well_known)).is_err(),
        "missing version must be rejected"
    );
}

#[test]
fn parse_well_known_rejects_malformed_transport_endpoint() {
    let identity = AgentIdentity::create("agent:badhint@demo").expect("identity");
    let identity_document = identity
        .build_identity_document(
            Some("https://agent.demo.example/messages"),
            &[],
            "self_asserted",
            None,
            365,
            None,
            None,
            Some("https"),
            None,
        )
        .expect("identity document");
    let mut well_known =
        build_well_known_document(&identity_document, "https://agent.demo.example", None, None)
            .expect("well-known document");
    let transports = well_known
        .get_mut("transports")
        .and_then(Value::as_object_mut)
        .expect("transports object");
    let http_hint = transports
        .get_mut("http")
        .and_then(Value::as_object_mut)
        .expect("http transport hint");
    http_hint.insert(
        "endpoint".to_string(),
        Value::String("not-a-url".to_string()),
    );

    assert!(
        parse_well_known_document(&Value::Object(well_known)).is_err(),
        "malformed transport endpoint must be rejected"
    );
}
