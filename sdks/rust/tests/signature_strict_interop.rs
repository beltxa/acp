use std::collections::HashMap;

use acp_runtime::crypto;
use acp_runtime::json_support;
use acp_runtime::messages::{Envelope, MessageClass};
use base64::Engine;
use base64::engine::general_purpose::{URL_SAFE, URL_SAFE_NO_PAD};
use serde_json::{Map, Value, json};

#[test]
fn verify_rejects_legacy_null_optional_signature_input() {
    let (sender_signing_private, sender_signing_public) = crypto::generate_ed25519_keypair();
    let (_recipient_encryption_private, recipient_encryption_public) =
        crypto::generate_x25519_keypair();
    let envelope = Envelope::build(
        "agent:sender@demo",
        vec!["agent:recipient@demo".to_string()],
        MessageClass::Send,
        "ctx:signature-strict",
        300,
        Some("op:signature-strict".to_string()),
        None,
        None,
        None,
        None,
    )
    .expect("envelope should be created");

    let mut payload = Map::new();
    payload.insert("type".to_string(), Value::String("ping".to_string()));
    payload.insert("message".to_string(), Value::String("hello".to_string()));

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
        "sig:strict",
    )
    .expect("payload signature should succeed");

    assert!(
        crypto::verify_protected_payload_signature(&envelope, &protected, &sender_signing_public),
        "canonical signature input should verify",
    );

    let mut legacy_envelope =
        serde_json::to_value(&envelope).expect("envelope serialization should succeed");
    match &mut legacy_envelope {
        Value::Object(map) => {
            map.insert("correlation_id".to_string(), Value::Null);
            map.insert("in_reply_to".to_string(), Value::Null);
        }
        _ => panic!("serialized envelope must be an object"),
    }

    let legacy_signature_input = json_support::canonical_json_bytes(&json!({
        "envelope": legacy_envelope,
        "protected": protected.to_signable_value(),
    }))
    .expect("legacy signature input should serialize");
    let legacy_signature =
        crypto::sign_bytes(&legacy_signature_input, &sender_signing_private).expect("sign");

    let mut legacy_protected = protected.clone();
    legacy_protected.signature = legacy_signature;
    assert!(
        !crypto::verify_protected_payload_signature(
            &envelope,
            &legacy_protected,
            &sender_signing_public,
        ),
        "legacy null-optional signature input must be rejected",
    );
}

#[test]
fn b64_decode_accepts_url_safe_padded_and_unpadded() {
    let payload = b"acp-signature-interop";
    let padded = URL_SAFE.encode(payload);
    let unpadded = URL_SAFE_NO_PAD.encode(payload);

    assert_eq!(
        crypto::b64_decode(&padded).expect("padded URL-safe base64 should decode"),
        payload
    );
    assert_eq!(
        crypto::b64_decode(&unpadded).expect("unpadded URL-safe base64 should decode"),
        payload
    );
}
