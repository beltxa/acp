/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import {
  createCipheriv,
  createDecipheriv,
  createHash,
  hkdfSync,
  randomBytes
} from "node:crypto";
import nacl from "tweetnacl";
import { cryptoError } from "./errors";
import { canonicalJsonBytes, JsonMap, JsonValue, parseJsonMap } from "./jsonSupport";
import { Envelope, ProtectedPayload, WrappedContentKey } from "./messages";

function toBase64Url(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64url");
}

function fromBase64Url(value: string): Uint8Array {
  try {
    return Buffer.from(value, "base64url");
  } catch (error) {
    throw cryptoError(`invalid base64 value: ${String(error)}`);
  }
}

function asFixedBytes(value: Uint8Array, length: number, label: string): Uint8Array {
  if (value.length !== length) {
    throw cryptoError(`invalid ${label} length`);
  }
  return value;
}

export function sha256Hex(input: Uint8Array): string {
  return createHash("sha256").update(input).digest("hex");
}

export function generateEd25519Keypair(): { private_key: string; public_key: string } {
  const seed = randomBytes(32);
  const keypair = nacl.sign.keyPair.fromSeed(seed);
  return {
    private_key: toBase64Url(seed),
    public_key: toBase64Url(keypair.publicKey)
  };
}

export function ed25519PublicFromPrivate(signingPrivateKeyB64: string): string {
  const seed = asFixedBytes(fromBase64Url(signingPrivateKeyB64), 32, "Ed25519 private key");
  return toBase64Url(nacl.sign.keyPair.fromSeed(seed).publicKey);
}

export function generateX25519Keypair(): { private_key: string; public_key: string } {
  const keypair = nacl.box.keyPair();
  return {
    private_key: toBase64Url(keypair.secretKey),
    public_key: toBase64Url(keypair.publicKey)
  };
}

export function x25519PublicFromPrivate(encryptionPrivateKeyB64: string): string {
  const privateKey = asFixedBytes(fromBase64Url(encryptionPrivateKeyB64), 32, "X25519 private key");
  const keypair = nacl.box.keyPair.fromSecretKey(privateKey);
  return toBase64Url(keypair.publicKey);
}

export function signBytes(data: Uint8Array, signingPrivateKeyB64: string): string {
  const seed = asFixedBytes(fromBase64Url(signingPrivateKeyB64), 32, "Ed25519 private key");
  const signingKeypair = nacl.sign.keyPair.fromSeed(seed);
  const signature = nacl.sign.detached(data, signingKeypair.secretKey);
  return toBase64Url(signature);
}

export function verifySignature(
  data: Uint8Array,
  signatureB64: string,
  signingPublicKeyB64: string
): boolean {
  const signature = fromBase64Url(signatureB64);
  const publicKey = fromBase64Url(signingPublicKeyB64);
  if (signature.length !== nacl.sign.signatureLength || publicKey.length !== nacl.sign.publicKeyLength) {
    return false;
  }
  return nacl.sign.detached.verify(data, signature, publicKey);
}

export function envelopeAad(envelope: Envelope): Uint8Array {
  return canonicalJsonBytes({
    acp_version: envelope.acp_version,
    message_id: envelope.message_id,
    operation_id: envelope.operation_id,
    sender: envelope.sender,
    recipients: envelope.recipients
  });
}

function deriveWrapKey(sharedSecret: Uint8Array, recipient: string): Uint8Array {
  const derived = hkdfSync("sha256", sharedSecret, Buffer.alloc(0), `acp-v1-wrap:${recipient}`, 32);
  return new Uint8Array(derived);
}

function encryptAesGcm(
  key: Uint8Array,
  nonce: Uint8Array,
  plaintext: Uint8Array,
  aad: Uint8Array
): Uint8Array {
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  cipher.setAAD(aad);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return Buffer.concat([ciphertext, authTag]);
}

function decryptAesGcm(
  key: Uint8Array,
  nonce: Uint8Array,
  ciphertextWithTag: Uint8Array,
  aad: Uint8Array
): Uint8Array {
  if (ciphertextWithTag.length < 16) {
    throw cryptoError("ciphertext is too short");
  }
  const ciphertext = ciphertextWithTag.subarray(0, ciphertextWithTag.length - 16);
  const tag = ciphertextWithTag.subarray(ciphertextWithTag.length - 16);
  const decipher = createDecipheriv("aes-256-gcm", key, nonce);
  decipher.setAAD(aad);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}

export function encryptForRecipients(
  payload: JsonMap,
  envelope: Envelope,
  recipientEncryptionPublicKeys: Record<string, string>
): ProtectedPayload {
  const plaintext = canonicalJsonBytes(payload as JsonValue);
  const contentKey = randomBytes(32);
  const payloadNonce = randomBytes(12);
  const payloadCiphertext = encryptAesGcm(contentKey, payloadNonce, plaintext, envelopeAad(envelope));

  const ephemeral = nacl.box.keyPair();
  const wrappedContentKeys: WrappedContentKey[] = [];
  for (const [recipient, recipientPublicKeyB64] of Object.entries(recipientEncryptionPublicKeys)) {
    const recipientPublicKey = asFixedBytes(
      fromBase64Url(recipientPublicKeyB64),
      32,
      "X25519 public key"
    );
    const sharedSecret = nacl.scalarMult(ephemeral.secretKey, recipientPublicKey);
    const wrapKey = deriveWrapKey(sharedSecret, recipient);
    const wrapNonce = randomBytes(12);
    const wrappedContentKey = encryptAesGcm(
      wrapKey,
      wrapNonce,
      contentKey,
      new TextEncoder().encode(envelope.message_id)
    );
    wrappedContentKeys.push({
      recipient,
      ephemeral_public_key: toBase64Url(ephemeral.publicKey),
      nonce: toBase64Url(wrapNonce),
      ciphertext: toBase64Url(wrappedContentKey)
    });
  }

  return {
    nonce: toBase64Url(payloadNonce),
    ciphertext: toBase64Url(payloadCiphertext),
    wrapped_content_keys: wrappedContentKeys,
    payload_hash: sha256Hex(payloadCiphertext),
    signature_kid: "",
    signature: ""
  };
}

function messageSignatureInput(envelope: Envelope, protectedPayload: ProtectedPayload): Uint8Array {
  const signableProtected: JsonMap = {
    nonce: protectedPayload.nonce,
    ciphertext: protectedPayload.ciphertext,
    wrapped_content_keys: [...protectedPayload.wrapped_content_keys].sort((a, b) =>
      a.recipient.localeCompare(b.recipient)
    ) as unknown as JsonValue,
    payload_hash: protectedPayload.payload_hash,
    signature_kid: protectedPayload.signature_kid
  };
  return canonicalJsonBytes({
    envelope,
    protected: signableProtected
  } as unknown as JsonValue);
}

export function signProtectedPayload(
  envelope: Envelope,
  protectedPayload: ProtectedPayload,
  signingPrivateKeyB64: string,
  signatureKid: string
): ProtectedPayload {
  const signedPayload: ProtectedPayload = {
    ...protectedPayload,
    signature_kid: signatureKid
  };
  const signatureInput = messageSignatureInput(envelope, signedPayload);
  signedPayload.signature = signBytes(signatureInput, signingPrivateKeyB64);
  return signedPayload;
}

export function verifyProtectedPayloadSignature(
  envelope: Envelope,
  protectedPayload: ProtectedPayload,
  senderSigningPublicKeyB64: string
): boolean {
  if (!protectedPayload.signature.trim()) {
    return false;
  }
  const signatureInput = messageSignatureInput(envelope, protectedPayload);
  return verifySignature(signatureInput, protectedPayload.signature, senderSigningPublicKeyB64);
}

export function decryptForRecipient(
  envelope: Envelope,
  protectedPayload: ProtectedPayload,
  recipientId: string,
  recipientEncryptionPrivateKeyB64: string
): JsonMap {
  const wrapped = protectedPayload.wrapped_content_keys.find((item) => item.recipient === recipientId);
  if (!wrapped) {
    throw cryptoError(`No wrapped content key available for recipient ${recipientId}`);
  }
  const recipientPrivateKey = asFixedBytes(
    fromBase64Url(recipientEncryptionPrivateKeyB64),
    32,
    "X25519 private key"
  );
  const ephemeralPublicKey = asFixedBytes(
    fromBase64Url(wrapped.ephemeral_public_key),
    32,
    "X25519 public key"
  );
  const sharedSecret = nacl.scalarMult(recipientPrivateKey, ephemeralPublicKey);
  const wrapKey = deriveWrapKey(sharedSecret, recipientId);
  const wrappedNonce = asFixedBytes(fromBase64Url(wrapped.nonce), 12, "wrapped nonce");
  const wrappedCiphertext = fromBase64Url(wrapped.ciphertext);
  const contentKey = decryptAesGcm(
    wrapKey,
    wrappedNonce,
    wrappedCiphertext,
    new TextEncoder().encode(envelope.message_id)
  );
  const payloadNonce = asFixedBytes(fromBase64Url(protectedPayload.nonce), 12, "payload nonce");
  const payloadCiphertext = fromBase64Url(protectedPayload.ciphertext);
  const plaintext = decryptAesGcm(contentKey, payloadNonce, payloadCiphertext, envelopeAad(envelope));
  return parseJsonMap(new TextDecoder().decode(plaintext));
}
