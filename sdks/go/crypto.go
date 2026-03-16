package acp

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"sort"

	"golang.org/x/crypto/curve25519"
	"golang.org/x/crypto/hkdf"
)

func toBase64URL(bytes []byte) string {
	return base64.RawURLEncoding.EncodeToString(bytes)
}

func fromBase64URL(value string) ([]byte, error) {
	decoded, err := base64.RawURLEncoding.DecodeString(value)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("invalid base64 value: %v", err))
	}
	return decoded, nil
}

func asFixedBytes(value []byte, length int, label string) ([]byte, error) {
	if len(value) != length {
		return nil, CryptoError(fmt.Sprintf("invalid %s length", label))
	}
	return value, nil
}

func SHA256Hex(input []byte) string {
	sum := sha256.Sum256(input)
	return hex.EncodeToString(sum[:])
}

func GenerateEd25519Keypair() (privateKey string, publicKey string, err error) {
	seed := make([]byte, ed25519.SeedSize)
	if _, err := rand.Read(seed); err != nil {
		return "", "", CryptoError(fmt.Sprintf("unable to generate Ed25519 seed: %v", err))
	}
	key := ed25519.NewKeyFromSeed(seed)
	public := key.Public().(ed25519.PublicKey)
	return toBase64URL(seed), toBase64URL(public), nil
}

func Ed25519PublicFromPrivate(signingPrivateKeyB64 string) (string, error) {
	seed, err := fromBase64URL(signingPrivateKeyB64)
	if err != nil {
		return "", err
	}
	seed, err = asFixedBytes(seed, ed25519.SeedSize, "Ed25519 private key")
	if err != nil {
		return "", err
	}
	key := ed25519.NewKeyFromSeed(seed)
	return toBase64URL(key.Public().(ed25519.PublicKey)), nil
}

func GenerateX25519Keypair() (privateKey string, publicKey string, err error) {
	privateBytes := make([]byte, 32)
	if _, err := rand.Read(privateBytes); err != nil {
		return "", "", CryptoError(fmt.Sprintf("unable to generate X25519 private key: %v", err))
	}
	publicBytes, err := curve25519.X25519(privateBytes, curve25519.Basepoint)
	if err != nil {
		return "", "", CryptoError(fmt.Sprintf("unable to derive X25519 public key: %v", err))
	}
	return toBase64URL(privateBytes), toBase64URL(publicBytes), nil
}

func X25519PublicFromPrivate(encryptionPrivateKeyB64 string) (string, error) {
	privateBytes, err := fromBase64URL(encryptionPrivateKeyB64)
	if err != nil {
		return "", err
	}
	privateBytes, err = asFixedBytes(privateBytes, 32, "X25519 private key")
	if err != nil {
		return "", err
	}
	publicBytes, err := curve25519.X25519(privateBytes, curve25519.Basepoint)
	if err != nil {
		return "", CryptoError(fmt.Sprintf("unable to derive X25519 public key: %v", err))
	}
	return toBase64URL(publicBytes), nil
}

func SignBytes(data []byte, signingPrivateKeyB64 string) (string, error) {
	seed, err := fromBase64URL(signingPrivateKeyB64)
	if err != nil {
		return "", err
	}
	seed, err = asFixedBytes(seed, ed25519.SeedSize, "Ed25519 private key")
	if err != nil {
		return "", err
	}
	signingKey := ed25519.NewKeyFromSeed(seed)
	signature := ed25519.Sign(signingKey, data)
	return toBase64URL(signature), nil
}

func VerifySignature(data []byte, signatureB64 string, signingPublicKeyB64 string) bool {
	signature, err := fromBase64URL(signatureB64)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return false
	}
	publicKey, err := fromBase64URL(signingPublicKeyB64)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return false
	}
	return ed25519.Verify(ed25519.PublicKey(publicKey), data, signature)
}

func EnvelopeAAD(envelope Envelope) ([]byte, error) {
	return CanonicalJSONBytes(map[string]any{
		"acp_version":  envelope.ACPVersion,
		"message_id":   envelope.MessageID,
		"operation_id": envelope.OperationID,
		"sender":       envelope.Sender,
		"recipients":   envelope.Recipients,
	})
}

func deriveWrapKey(sharedSecret []byte, recipient string) ([]byte, error) {
	reader := hkdf.New(sha256.New, sharedSecret, []byte{}, []byte("acp-v1-wrap:"+recipient))
	key := make([]byte, 32)
	if _, err := io.ReadFull(reader, key); err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to derive wrap key: %v", err))
	}
	return key, nil
}

func encryptAESGCM(key []byte, nonce []byte, plaintext []byte, aad []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to create AES cipher: %v", err))
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to create AES-GCM cipher: %v", err))
	}
	if len(nonce) != gcm.NonceSize() {
		return nil, CryptoError("invalid nonce length")
	}
	return gcm.Seal(nil, nonce, plaintext, aad), nil
}

func decryptAESGCM(key []byte, nonce []byte, ciphertext []byte, aad []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to create AES cipher: %v", err))
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to create AES-GCM cipher: %v", err))
	}
	if len(nonce) != gcm.NonceSize() {
		return nil, CryptoError("invalid nonce length")
	}
	plaintext, err := gcm.Open(nil, nonce, ciphertext, aad)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to decrypt AES-GCM payload: %v", err))
	}
	return plaintext, nil
}

func randomBytes(length int) ([]byte, error) {
	out := make([]byte, length)
	if _, err := rand.Read(out); err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to generate secure random bytes: %v", err))
	}
	return out, nil
}

func EncryptForRecipients(
	payload map[string]any,
	envelope Envelope,
	recipientEncryptionPublicKeys map[string]string,
) (ProtectedPayload, error) {
	plaintext, err := CanonicalJSONBytes(payload)
	if err != nil {
		return ProtectedPayload{}, err
	}
	contentKey, err := randomBytes(32)
	if err != nil {
		return ProtectedPayload{}, err
	}
	payloadNonce, err := randomBytes(12)
	if err != nil {
		return ProtectedPayload{}, err
	}
	aad, err := EnvelopeAAD(envelope)
	if err != nil {
		return ProtectedPayload{}, err
	}
	payloadCiphertext, err := encryptAESGCM(contentKey, payloadNonce, plaintext, aad)
	if err != nil {
		return ProtectedPayload{}, err
	}
	ephemeralPrivate, ephemeralPublic, err := GenerateX25519Keypair()
	if err != nil {
		return ProtectedPayload{}, err
	}
	ephemeralPrivateBytes, _ := fromBase64URL(ephemeralPrivate)
	wrapped := make([]WrappedContentKey, 0, len(recipientEncryptionPublicKeys))
	recipients := make([]string, 0, len(recipientEncryptionPublicKeys))
	for recipient := range recipientEncryptionPublicKeys {
		recipients = append(recipients, recipient)
	}
	sort.Strings(recipients)
	for _, recipient := range recipients {
		recipientPublicB64 := recipientEncryptionPublicKeys[recipient]
		recipientPublicBytes, err := fromBase64URL(recipientPublicB64)
		if err != nil {
			return ProtectedPayload{}, err
		}
		recipientPublicBytes, err = asFixedBytes(recipientPublicBytes, 32, "X25519 public key")
		if err != nil {
			return ProtectedPayload{}, err
		}
		sharedSecret, err := curve25519.X25519(ephemeralPrivateBytes, recipientPublicBytes)
		if err != nil {
			return ProtectedPayload{}, CryptoError(fmt.Sprintf("unable to derive X25519 shared secret: %v", err))
		}
		wrapKey, err := deriveWrapKey(sharedSecret, recipient)
		if err != nil {
			return ProtectedPayload{}, err
		}
		wrapNonce, err := randomBytes(12)
		if err != nil {
			return ProtectedPayload{}, err
		}
		wrappedCiphertext, err := encryptAESGCM(wrapKey, wrapNonce, contentKey, []byte(envelope.MessageID))
		if err != nil {
			return ProtectedPayload{}, err
		}
		wrapped = append(wrapped, WrappedContentKey{
			Recipient:          recipient,
			EphemeralPublicKey: ephemeralPublic,
			Nonce:              toBase64URL(wrapNonce),
			Ciphertext:         toBase64URL(wrappedCiphertext),
		})
	}
	return ProtectedPayload{
		Nonce:              toBase64URL(payloadNonce),
		Ciphertext:         toBase64URL(payloadCiphertext),
		WrappedContentKeys: wrapped,
		PayloadHash:        SHA256Hex(payloadCiphertext),
		SignatureKID:       "",
		Signature:          "",
	}, nil
}

func messageSignatureInput(envelope Envelope, protectedPayload ProtectedPayload) ([]byte, error) {
	wrapped := append([]WrappedContentKey{}, protectedPayload.WrappedContentKeys...)
	sort.Slice(wrapped, func(left int, right int) bool {
		return wrapped[left].Recipient < wrapped[right].Recipient
	})
	signable := map[string]any{
		"envelope": envelope,
		"protected": map[string]any{
			"nonce":                protectedPayload.Nonce,
			"ciphertext":           protectedPayload.Ciphertext,
			"wrapped_content_keys": wrapped,
			"payload_hash":         protectedPayload.PayloadHash,
			"signature_kid":        protectedPayload.SignatureKID,
		},
	}
	return CanonicalJSONBytes(signable)
}

func SignProtectedPayload(
	envelope Envelope,
	protectedPayload ProtectedPayload,
	signingPrivateKeyB64 string,
	signatureKID string,
) (ProtectedPayload, error) {
	signed := protectedPayload
	signed.SignatureKID = signatureKID
	input, err := messageSignatureInput(envelope, signed)
	if err != nil {
		return ProtectedPayload{}, err
	}
	signature, err := SignBytes(input, signingPrivateKeyB64)
	if err != nil {
		return ProtectedPayload{}, err
	}
	signed.Signature = signature
	return signed, nil
}

func VerifyProtectedPayloadSignature(
	envelope Envelope,
	protectedPayload ProtectedPayload,
	senderSigningPublicKeyB64 string,
) bool {
	if protectedPayload.Signature == "" {
		return false
	}
	input, err := messageSignatureInput(envelope, protectedPayload)
	if err != nil {
		return false
	}
	return VerifySignature(input, protectedPayload.Signature, senderSigningPublicKeyB64)
}

func DecryptForRecipient(
	envelope Envelope,
	protectedPayload ProtectedPayload,
	recipientID string,
	recipientEncryptionPrivateKeyB64 string,
) (map[string]any, error) {
	var wrapped *WrappedContentKey
	for index := range protectedPayload.WrappedContentKeys {
		if protectedPayload.WrappedContentKeys[index].Recipient == recipientID {
			wrapped = &protectedPayload.WrappedContentKeys[index]
			break
		}
	}
	if wrapped == nil {
		return nil, CryptoError(fmt.Sprintf("No wrapped content key available for recipient %s", recipientID))
	}
	recipientPrivate, err := fromBase64URL(recipientEncryptionPrivateKeyB64)
	if err != nil {
		return nil, err
	}
	recipientPrivate, err = asFixedBytes(recipientPrivate, 32, "X25519 private key")
	if err != nil {
		return nil, err
	}
	ephemeralPublic, err := fromBase64URL(wrapped.EphemeralPublicKey)
	if err != nil {
		return nil, err
	}
	ephemeralPublic, err = asFixedBytes(ephemeralPublic, 32, "X25519 public key")
	if err != nil {
		return nil, err
	}
	sharedSecret, err := curve25519.X25519(recipientPrivate, ephemeralPublic)
	if err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to derive X25519 shared secret: %v", err))
	}
	wrapKey, err := deriveWrapKey(sharedSecret, recipientID)
	if err != nil {
		return nil, err
	}
	wrapNonce, err := fromBase64URL(wrapped.Nonce)
	if err != nil {
		return nil, err
	}
	wrapNonce, err = asFixedBytes(wrapNonce, 12, "wrapped nonce")
	if err != nil {
		return nil, err
	}
	wrappedCiphertext, err := fromBase64URL(wrapped.Ciphertext)
	if err != nil {
		return nil, err
	}
	contentKey, err := decryptAESGCM(wrapKey, wrapNonce, wrappedCiphertext, []byte(envelope.MessageID))
	if err != nil {
		return nil, err
	}
	payloadNonce, err := fromBase64URL(protectedPayload.Nonce)
	if err != nil {
		return nil, err
	}
	payloadNonce, err = asFixedBytes(payloadNonce, 12, "payload nonce")
	if err != nil {
		return nil, err
	}
	payloadCiphertext, err := fromBase64URL(protectedPayload.Ciphertext)
	if err != nil {
		return nil, err
	}
	aad, err := EnvelopeAAD(envelope)
	if err != nil {
		return nil, err
	}
	plaintext, err := decryptAESGCM(contentKey, payloadNonce, payloadCiphertext, aad)
	if err != nil {
		return nil, err
	}
	var parsed map[string]any
	if err := json.Unmarshal(plaintext, &parsed); err != nil {
		return nil, CryptoError(fmt.Sprintf("unable to parse decrypted payload: %v", err))
	}
	return parsed, nil
}
