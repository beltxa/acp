use std::collections::HashMap;

use acp_runtime::crypto;
use acp_runtime::messages::{Envelope, MessageClass};
use serde_json::{Map, Value};

#[test]
fn encrypt_sign_verify_and_decrypt_roundtrip() {
    let (sender_signing_private, sender_signing_public) = crypto::generate_ed25519_keypair();
    let (recipient_encryption_private, recipient_encryption_public) =
        crypto::generate_x25519_keypair();
    let envelope = Envelope::build(
        "agent:sender@demo",
        vec!["agent:recipient@demo".to_string()],
        MessageClass::Send,
        "ctx:test",
        300,
        Some("op:roundtrip".to_string()),
        Some("tenant.demo".to_string()),
        None,
        None,
        None,
    )
    .expect("envelope should be created");
    assert_eq!(envelope.tenant.as_deref(), Some("tenant.demo"));

    let mut payload = Map::new();
    payload.insert("type".to_string(), Value::String("demo".to_string()));
    payload.insert("sequence".to_string(), Value::Number(1.into()));

    let recipient_keys = HashMap::from([(
        "agent:recipient@demo".to_string(),
        recipient_encryption_public.clone(),
    )]);
    let mut protected = crypto::encrypt_for_recipients(&payload, &envelope, &recipient_keys)
        .expect("payload encryption should succeed");
    crypto::sign_protected_payload(
        &envelope,
        &mut protected,
        &sender_signing_private,
        "sig:test",
    )
    .expect("payload signature should succeed");

    assert!(crypto::verify_protected_payload_signature(
        &envelope,
        &protected,
        &sender_signing_public
    ));

    let decrypted = crypto::decrypt_for_recipient(
        &envelope,
        &protected,
        "agent:recipient@demo",
        &recipient_encryption_private,
    )
    .expect("recipient decryption should succeed");

    assert_eq!(
        decrypted.get("type").and_then(Value::as_str),
        Some("demo"),
        "decrypted payload should preserve type field"
    );
    assert_eq!(
        decrypted.get("sequence").and_then(Value::as_i64),
        Some(1),
        "decrypted payload should preserve numeric field"
    );
}
