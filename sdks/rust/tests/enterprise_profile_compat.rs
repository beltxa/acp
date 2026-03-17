use std::fs;
use std::path::{Path, PathBuf};

use acp::options::AcpAgentOptions;
use serde_json::{Map, Value};

fn security_vectors_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("tests")
        .join("vectors")
        .join("security")
}

#[test]
fn reads_shared_enterprise_https_fixture_with_expected_schema() {
    let fixture = load_fixture("enterprise_profile_https.json");
    let options = AcpAgentOptions::from_config_map(Some(&fixture));

    assert_eq!("vault", options.key_provider);
    assert_eq!(
        Some("https://vault.company.net".to_string()),
        options.vault_url
    );
    assert_eq!(
        Some("secret/data/acp/identities".to_string()),
        options.vault_path
    );
    assert_eq!("VAULT_TOKEN", options.vault_token_env);
    assert!(!options.allow_insecure_http);
    assert!(!options.allow_insecure_tls);
    assert!(!options.mtls_enabled);
}

#[test]
fn reads_shared_enterprise_vault_mtls_fixture_with_provider_backed_material() {
    let fixture = load_fixture("enterprise_profile_vault_mtls.json");
    let options = AcpAgentOptions::from_config_map(Some(&fixture));

    assert_eq!("vault", options.key_provider);
    assert!(options.mtls_enabled);
    assert_eq!(
        Some("/etc/acp/ca/enterprise-ca.pem".to_string()),
        options.ca_file
    );
    assert_eq!(None, options.cert_file);
    assert_eq!(None, options.key_file);
}

#[test]
fn to_config_map_exports_aligned_enterprise_fields() {
    let options = AcpAgentOptions {
        key_provider: "vault".to_string(),
        vault_url: Some("https://vault.company.net".to_string()),
        vault_path: Some("secret/data/acp/identities".to_string()),
        vault_token_env: "VAULT_TOKEN".to_string(),
        allow_insecure_http: false,
        allow_insecure_tls: false,
        mtls_enabled: true,
        ca_file: Some("/etc/acp/ca/enterprise-ca.pem".to_string()),
        ..AcpAgentOptions::default()
    };

    let exported = options.to_config_map();
    assert_eq!(
        Some("vault"),
        exported.get("key_provider").and_then(Value::as_str)
    );
    assert_eq!(
        Some("https://vault.company.net"),
        exported.get("vault_url").and_then(Value::as_str)
    );
    assert_eq!(
        Some("secret/data/acp/identities"),
        exported.get("vault_path").and_then(Value::as_str)
    );
    assert_eq!(
        Some("VAULT_TOKEN"),
        exported.get("vault_token_env").and_then(Value::as_str)
    );
    assert_eq!(
        Some(false),
        exported.get("allow_insecure_http").and_then(Value::as_bool)
    );
    assert_eq!(
        Some(false),
        exported.get("allow_insecure_tls").and_then(Value::as_bool)
    );
    assert_eq!(
        Some(true),
        exported.get("mtls_enabled").and_then(Value::as_bool)
    );
    assert_eq!(
        Some("/etc/acp/ca/enterprise-ca.pem"),
        exported.get("ca_file").and_then(Value::as_str)
    );
}

#[test]
fn from_config_map_preserves_default_provider_values_when_unset() {
    let options = AcpAgentOptions::from_config_map(Some(&Map::new()));
    assert_eq!("local", options.key_provider);
    assert_eq!("VAULT_TOKEN", options.vault_token_env);
}

fn load_fixture(name: &str) -> Map<String, Value> {
    let path = security_vectors_dir().join(name);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("unable to read fixture {}: {err}", path.display()));
    serde_json::from_str::<Map<String, Value>>(&raw)
        .unwrap_or_else(|err| panic!("unable to parse fixture {}: {err}", path.display()))
}
