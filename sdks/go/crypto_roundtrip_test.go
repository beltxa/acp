package acp

import "testing"

func TestEncryptSignVerifyAndDecryptRoundtrip(t *testing.T) {
	senderSigningPrivate, senderSigningPublic, err := GenerateEd25519Keypair()
	if err != nil {
		t.Fatalf("unable to generate sender signing keys: %v", err)
	}
	recipientEncryptionPrivate, recipientEncryptionPublic, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("unable to generate recipient encryption keys: %v", err)
	}
	envelope, err := BuildEnvelope(EnvelopeInput{
		Sender:           "agent:sender@demo",
		Recipients:       []string{"agent:recipient@demo"},
		MessageClass:     MessageSend,
		ContextID:        "ctx:test",
		ExpiresInSeconds: 300,
		OperationID:      "op:roundtrip",
		Tenant:           "tenant.demo",
	})
	if err != nil {
		t.Fatalf("envelope should be created: %v", err)
	}
	if envelope.Tenant == nil || *envelope.Tenant != "tenant.demo" {
		t.Fatalf("envelope tenant should be present")
	}
	payload := map[string]any{
		"type":     "demo",
		"sequence": float64(1),
	}
	protectedPayload, err := EncryptForRecipients(payload, envelope, map[string]string{
		"agent:recipient@demo": recipientEncryptionPublic,
	})
	if err != nil {
		t.Fatalf("payload encryption should succeed: %v", err)
	}
	protectedPayload, err = SignProtectedPayload(envelope, protectedPayload, senderSigningPrivate, "sig:test")
	if err != nil {
		t.Fatalf("payload signature should succeed: %v", err)
	}
	if !VerifyProtectedPayloadSignature(envelope, protectedPayload, senderSigningPublic) {
		t.Fatalf("signature verification should pass")
	}
	decrypted, err := DecryptForRecipient(envelope, protectedPayload, "agent:recipient@demo", recipientEncryptionPrivate)
	if err != nil {
		t.Fatalf("recipient decryption should succeed: %v", err)
	}
	if decrypted["type"] != "demo" {
		t.Fatalf("decrypted payload should preserve type field")
	}
	if int(asFloat64FromFixture(t, decrypted["sequence"], "sequence must be numeric")) != 1 {
		t.Fatalf("decrypted payload should preserve numeric field")
	}
}
