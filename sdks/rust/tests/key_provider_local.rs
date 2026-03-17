use acp::http_security::validate_http_url;
use acp::identity::{AgentIdentity, write_identity};
use acp::key_provider::{KeyProvider, LocalKeyProvider};

#[test]
fn local_key_provider_matches_stored_identity_material() {
    let temp = tempfile::tempdir().expect("tempdir");
    let agent_id = "agent:ricardo@demo";
    let identity = AgentIdentity::create(agent_id).expect("identity");
    let identity_document = identity
        .build_identity_document(
            Some("https://localhost:9000/messages"),
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
    write_identity(temp.path(), &identity, &identity_document).expect("write identity");

    let provider = LocalKeyProvider::new(temp.path().to_path_buf(), None, None, None);
    let keys = provider
        .load_identity_keys(agent_id)
        .expect("provider identity keys");

    assert_eq!(keys.signing_private_key, identity.signing_private_key);
    assert_eq!(keys.encryption_private_key, identity.encryption_private_key);
    assert_eq!(
        provider
            .describe()
            .get("provider")
            .and_then(serde_json::Value::as_str),
        Some("local")
    );
}

#[test]
fn https_first_url_validation_requires_explicit_http_override() {
    assert!(validate_http_url("https://example.com/messages", false, false, "test").is_ok());
    assert!(validate_http_url("http://example.com/messages", false, false, "test").is_err());
    assert!(validate_http_url("http://example.com/messages", true, false, "test").is_ok());
}
