// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE;
use ed25519_dalek::{Signer, Verifier};
use hkdf::Hkdf;
use rand::RngCore;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use x25519_dalek::{PublicKey as X25519PublicKey, StaticSecret};

use crate::errors::{AcpError, AcpResult};
use crate::json_support;
use crate::messages::{Envelope, ProtectedPayload, WrappedContentKey};

pub fn b64_encode(value: &[u8]) -> String {
    URL_SAFE.encode(value)
}

pub fn b64_decode(value: &str) -> AcpResult<Vec<u8>> {
    URL_SAFE
        .decode(value.as_bytes())
        .map_err(|e| AcpError::Crypto(format!("invalid base64 value: {e}")))
}

pub fn canonical_json(value: &Value) -> AcpResult<String> {
    json_support::canonical_json_string(value)
}

pub fn sha256_hex(value: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(value);
    hex::encode(hasher.finalize())
}

pub fn generate_ed25519_keypair() -> (String, String) {
    let mut secret = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut secret);
    let signing_key = ed25519_dalek::SigningKey::from_bytes(&secret);
    let verify_key = signing_key.verifying_key();
    (
        b64_encode(&signing_key.to_bytes()),
        b64_encode(&verify_key.to_bytes()),
    )
}

pub fn generate_x25519_keypair() -> (String, String) {
    let mut secret = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut secret);
    let private_key = StaticSecret::from(secret);
    let public_key = X25519PublicKey::from(&private_key);
    (
        b64_encode(&private_key.to_bytes()),
        b64_encode(public_key.as_bytes()),
    )
}

pub fn sign_bytes(data: &[u8], signing_private_key_b64: &str) -> AcpResult<String> {
    let key_bytes = b64_decode(signing_private_key_b64)?;
    let key_bytes: [u8; 32] = key_bytes
        .try_into()
        .map_err(|_| AcpError::Crypto("invalid Ed25519 private key length".to_string()))?;
    let signing_key = ed25519_dalek::SigningKey::from_bytes(&key_bytes);
    Ok(b64_encode(&signing_key.sign(data).to_bytes()))
}

pub fn verify_signature(data: &[u8], signature_b64: &str, signing_public_key_b64: &str) -> bool {
    let Ok(signature_bytes) = b64_decode(signature_b64) else {
        return false;
    };
    let Ok(signature_bytes) = <[u8; 64]>::try_from(signature_bytes) else {
        return false;
    };
    let Ok(public_key_bytes) = b64_decode(signing_public_key_b64) else {
        return false;
    };
    let Ok(public_key_bytes) = <[u8; 32]>::try_from(public_key_bytes) else {
        return false;
    };
    let Ok(signature) = ed25519_dalek::Signature::try_from(signature_bytes.as_slice()) else {
        return false;
    };
    let Ok(verifying_key) = ed25519_dalek::VerifyingKey::from_bytes(&public_key_bytes) else {
        return false;
    };
    verifying_key.verify(data, &signature).is_ok()
}

pub fn envelope_aad(envelope: &Envelope) -> AcpResult<Vec<u8>> {
    let mut aad = Map::new();
    aad.insert(
        "acp_version".to_string(),
        Value::String(envelope.acp_version.clone()),
    );
    aad.insert(
        "message_id".to_string(),
        Value::String(envelope.message_id.clone()),
    );
    aad.insert(
        "operation_id".to_string(),
        Value::String(envelope.operation_id.clone()),
    );
    aad.insert("sender".to_string(), Value::String(envelope.sender.clone()));
    aad.insert(
        "recipients".to_string(),
        Value::Array(
            envelope
                .recipients
                .iter()
                .map(|recipient| Value::String(recipient.clone()))
                .collect(),
        ),
    );
    if let Some(tenant) = envelope.tenant.as_ref() {
        aad.insert("tenant".to_string(), Value::String(tenant.clone()));
    }
    json_support::canonical_json_bytes(&Value::Object(aad))
}

pub fn encrypt_for_recipients(
    payload: &Map<String, Value>,
    envelope: &Envelope,
    recipient_encryption_public_keys: &HashMap<String, String>,
) -> AcpResult<ProtectedPayload> {
    let plaintext = canonical_json(&Value::Object(payload.clone()))?.into_bytes();
    let mut content_key = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut content_key);
    let mut nonce = [0u8; 12];
    rand::thread_rng().fill_bytes(&mut nonce);

    let payload_aad = envelope_aad(envelope)?;
    let payload_cipher = Aes256Gcm::new_from_slice(&content_key)
        .map_err(|e| AcpError::Crypto(format!("unable to initialize payload cipher: {e}")))?;
    let ciphertext = payload_cipher
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: &plaintext,
                aad: &payload_aad,
            },
        )
        .map_err(|e| AcpError::Crypto(format!("payload encryption failed: {e}")))?;

    let mut ephemeral_secret_bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut ephemeral_secret_bytes);
    let ephemeral_private = StaticSecret::from(ephemeral_secret_bytes);
    let ephemeral_public = X25519PublicKey::from(&ephemeral_private);

    let mut wrapped_content_keys = Vec::new();
    for (recipient, recipient_public_key_b64) in recipient_encryption_public_keys {
        let recipient_public = decode_x25519_public(recipient_public_key_b64)?;
        let shared_secret = ephemeral_private.diffie_hellman(&recipient_public);
        let wrap_key = derive_wrap_key(shared_secret.as_bytes(), recipient)?;
        let mut wrap_nonce = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut wrap_nonce);
        let wrap_cipher = Aes256Gcm::new_from_slice(&wrap_key)
            .map_err(|e| AcpError::Crypto(format!("unable to initialize wrap cipher: {e}")))?;
        let wrapped_cek = wrap_cipher
            .encrypt(
                Nonce::from_slice(&wrap_nonce),
                Payload {
                    msg: &content_key,
                    aad: envelope.message_id.as_bytes(),
                },
            )
            .map_err(|e| AcpError::Crypto(format!("content key wrap failed: {e}")))?;
        wrapped_content_keys.push(WrappedContentKey {
            recipient: recipient.to_string(),
            ephemeral_public_key: b64_encode(ephemeral_public.as_bytes()),
            nonce: b64_encode(&wrap_nonce),
            ciphertext: b64_encode(&wrapped_cek),
        });
    }

    Ok(ProtectedPayload {
        nonce: b64_encode(&nonce),
        ciphertext: b64_encode(&ciphertext),
        wrapped_content_keys,
        payload_hash: sha256_hex(&ciphertext),
        signature_kid: String::new(),
        signature: String::new(),
    })
}

pub fn sign_protected_payload(
    envelope: &Envelope,
    protected_payload: &mut ProtectedPayload,
    signing_private_key_b64: &str,
    signature_kid: &str,
) -> AcpResult<()> {
    protected_payload.signature_kid = signature_kid.to_string();
    let input = message_signature_input(envelope, protected_payload)?;
    protected_payload.signature = sign_bytes(&input, signing_private_key_b64)?;
    Ok(())
}

pub fn verify_protected_payload_signature(
    envelope: &Envelope,
    protected_payload: &ProtectedPayload,
    sender_signing_public_key_b64: &str,
) -> bool {
    if protected_payload.signature.trim().is_empty() {
        return false;
    }
    let Ok(input) = message_signature_input(envelope, protected_payload) else {
        return false;
    };
    verify_signature(
        &input,
        &protected_payload.signature,
        sender_signing_public_key_b64,
    )
}

pub fn decrypt_for_recipient(
    envelope: &Envelope,
    protected_payload: &ProtectedPayload,
    recipient_id: &str,
    recipient_encryption_private_key_b64: &str,
) -> AcpResult<Map<String, Value>> {
    let matching = protected_payload
        .wrapped_content_keys
        .iter()
        .find(|item| item.recipient == recipient_id)
        .ok_or_else(|| {
            AcpError::Crypto(format!(
                "No wrapped content key available for recipient {recipient_id}"
            ))
        })?;

    let recipient_private = decode_x25519_private(recipient_encryption_private_key_b64)?;
    let ephemeral_public = decode_x25519_public(&matching.ephemeral_public_key)?;
    let shared_secret = recipient_private.diffie_hellman(&ephemeral_public);
    let wrap_key = derive_wrap_key(shared_secret.as_bytes(), recipient_id)?;

    let wrap_cipher = Aes256Gcm::new_from_slice(&wrap_key)
        .map_err(|e| AcpError::Crypto(format!("unable to initialize wrap cipher: {e}")))?;
    let wrapped_nonce = b64_decode(&matching.nonce)?;
    let wrapped_nonce: [u8; 12] = wrapped_nonce
        .try_into()
        .map_err(|_| AcpError::Crypto("invalid wrapped nonce length".to_string()))?;
    let content_key = wrap_cipher
        .decrypt(
            Nonce::from_slice(&wrapped_nonce),
            Payload {
                msg: &b64_decode(&matching.ciphertext)?,
                aad: envelope.message_id.as_bytes(),
            },
        )
        .map_err(|e| AcpError::Crypto(format!("failed to unwrap content key: {e}")))?;

    let payload_cipher = Aes256Gcm::new_from_slice(&content_key)
        .map_err(|e| AcpError::Crypto(format!("unable to initialize payload cipher: {e}")))?;
    let payload_nonce = b64_decode(&protected_payload.nonce)?;
    let payload_nonce: [u8; 12] = payload_nonce
        .try_into()
        .map_err(|_| AcpError::Crypto("invalid payload nonce length".to_string()))?;
    let plaintext = payload_cipher
        .decrypt(
            Nonce::from_slice(&payload_nonce),
            Payload {
                msg: &b64_decode(&protected_payload.ciphertext)?,
                aad: &envelope_aad(envelope)?,
            },
        )
        .map_err(|e| AcpError::Crypto(format!("failed to decrypt message payload: {e}")))?;
    let payload_value: Value = serde_json::from_slice(&plaintext)?;
    match payload_value {
        Value::Object(map) => Ok(map),
        _ => Err(AcpError::Crypto(
            "decrypted payload is not a JSON object".to_string(),
        )),
    }
}

fn message_signature_input(
    envelope: &Envelope,
    protected: &ProtectedPayload,
) -> AcpResult<Vec<u8>> {
    let value = serde_json::json!({
        "envelope": envelope,
        "protected": protected.to_signable_value(),
    });
    json_support::canonical_json_bytes(&value)
}

fn decode_x25519_public(value: &str) -> AcpResult<X25519PublicKey> {
    let bytes = b64_decode(value)?;
    let bytes: [u8; 32] = bytes
        .try_into()
        .map_err(|_| AcpError::Crypto("invalid X25519 public key length".to_string()))?;
    Ok(X25519PublicKey::from(bytes))
}

fn decode_x25519_private(value: &str) -> AcpResult<StaticSecret> {
    let bytes = b64_decode(value)?;
    let bytes: [u8; 32] = bytes
        .try_into()
        .map_err(|_| AcpError::Crypto("invalid X25519 private key length".to_string()))?;
    Ok(StaticSecret::from(bytes))
}

fn derive_wrap_key(shared_secret: &[u8], recipient: &str) -> AcpResult<[u8; 32]> {
    let hkdf = Hkdf::<Sha256>::new(None, shared_secret);
    let mut out = [0u8; 32];
    hkdf.expand(format!("acp-v1-wrap:{recipient}").as_bytes(), &mut out)
        .map_err(|e| AcpError::Crypto(format!("hkdf expand failed: {e}")))?;
    Ok(out)
}
