import { describe, expect, it } from "vitest";
import {
  decryptForRecipient,
  encryptForRecipients,
  generateEd25519Keypair,
  generateX25519Keypair,
  signProtectedPayload,
  verifyProtectedPayloadSignature
} from "../src/crypto.js";
import { buildEnvelope } from "../src/messages.js";

describe("Crypto roundtrip", () => {
  it("encrypts, signs, verifies, and decrypts payload", () => {
    const senderSigning = generateEd25519Keypair();
    const recipientEncryption = generateX25519Keypair();
    const envelope = buildEnvelope({
      sender: "agent:sender@demo",
      recipients: ["agent:recipient@demo"],
      message_class: "SEND",
      context_id: "ctx:test",
      expires_in_seconds: 120,
      operation_id: "op:test"
    });
    const payload = {
      kind: "demo",
      sequence: 1
    };
    const encrypted = encryptForRecipients(payload, envelope, {
      "agent:recipient@demo": recipientEncryption.public_key
    });
    const signed = signProtectedPayload(envelope, encrypted, senderSigning.private_key, "sig:test");
    expect(verifyProtectedPayloadSignature(envelope, signed, senderSigning.public_key)).toBe(true);
    const decrypted = decryptForRecipient(
      envelope,
      signed,
      "agent:recipient@demo",
      recipientEncryption.private_key
    );
    expect(decrypted.kind).toBe("demo");
    expect(decrypted.sequence).toBe(1);
  });
});
