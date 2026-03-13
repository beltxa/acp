package org.acp.client;

import org.bouncycastle.crypto.agreement.X25519Agreement;
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters;
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters;
import org.bouncycastle.crypto.params.X25519PrivateKeyParameters;
import org.bouncycastle.crypto.params.X25519PublicKeyParameters;
import org.bouncycastle.crypto.signers.Ed25519Signer;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class CryptoSupport {
    private static final SecureRandom RANDOM = new SecureRandom();

    private CryptoSupport() {
    }

    public static KeyMaterial generateEd25519Keypair() {
        Ed25519PrivateKeyParameters privateKey = new Ed25519PrivateKeyParameters(RANDOM);
        Ed25519PublicKeyParameters publicKey = privateKey.generatePublicKey();
        return new KeyMaterial(
            base64UrlEncode(privateKey.getEncoded()),
            base64UrlEncode(publicKey.getEncoded())
        );
    }

    public static KeyMaterial generateX25519Keypair() {
        X25519PrivateKeyParameters privateKey = new X25519PrivateKeyParameters(RANDOM);
        X25519PublicKeyParameters publicKey = privateKey.generatePublicKey();
        return new KeyMaterial(
            base64UrlEncode(privateKey.getEncoded()),
            base64UrlEncode(publicKey.getEncoded())
        );
    }

    public static String signBytes(byte[] data, String signingPrivateKeyB64) {
        Ed25519PrivateKeyParameters privateKey = new Ed25519PrivateKeyParameters(base64UrlDecode(signingPrivateKeyB64), 0);
        Ed25519Signer signer = new Ed25519Signer();
        signer.init(true, privateKey);
        signer.update(data, 0, data.length);
        return base64UrlEncode(signer.generateSignature());
    }

    public static boolean verifySignature(byte[] data, String signatureB64, String signingPublicKeyB64) {
        try {
            Ed25519PublicKeyParameters publicKey = new Ed25519PublicKeyParameters(base64UrlDecode(signingPublicKeyB64), 0);
            Ed25519Signer verifier = new Ed25519Signer();
            verifier.init(false, publicKey);
            verifier.update(data, 0, data.length);
            return verifier.verifySignature(base64UrlDecode(signatureB64));
        } catch (Exception exc) {
            return false;
        }
    }

    public static byte[] envelopeAad(Envelope envelope) {
        Map<String, Object> aad = new HashMap<>();
        aad.put("acp_version", envelope.getAcpVersion());
        aad.put("message_id", envelope.getMessageId());
        aad.put("operation_id", envelope.getOperationId());
        aad.put("sender", envelope.getSender());
        aad.put("recipients", envelope.getRecipients());
        return CanonicalJson.bytes(aad);
    }

    public static ProtectedPayload encryptForRecipients(
        Map<String, Object> payload,
        Envelope envelope,
        Map<String, String> recipientEncryptionPublicKeys
    ) {
        byte[] plaintext = CanonicalJson.bytes(payload);
        byte[] contentKey = randomBytes(32);
        byte[] nonce = randomBytes(12);
        byte[] payloadAad = envelopeAad(envelope);
        byte[] ciphertext = aesGcmEncrypt(contentKey, nonce, plaintext, payloadAad);

        X25519PrivateKeyParameters ephemeralPrivate = new X25519PrivateKeyParameters(RANDOM);
        byte[] ephemeralPublic = ephemeralPrivate.generatePublicKey().getEncoded();

        List<WrappedContentKey> wrapped = new ArrayList<>();
        for (Map.Entry<String, String> entry : recipientEncryptionPublicKeys.entrySet()) {
            String recipient = entry.getKey();
            byte[] recipientPublic = base64UrlDecode(entry.getValue());
            byte[] sharedSecret = x25519SharedSecret(ephemeralPrivate, recipientPublic);
            byte[] wrapKey = hkdfSha256(sharedSecret, ("acp-v1-wrap:" + recipient).getBytes(StandardCharsets.UTF_8), 32);
            byte[] wrapNonce = randomBytes(12);
            byte[] wrappedCek = aesGcmEncrypt(
                wrapKey,
                wrapNonce,
                contentKey,
                envelope.getMessageId().getBytes(StandardCharsets.UTF_8)
            );
            wrapped.add(
                new WrappedContentKey(
                    recipient,
                    base64UrlEncode(ephemeralPublic),
                    base64UrlEncode(wrapNonce),
                    base64UrlEncode(wrappedCek)
                )
            );
        }

        ProtectedPayload protectedPayload = new ProtectedPayload();
        protectedPayload.setNonce(base64UrlEncode(nonce));
        protectedPayload.setCiphertext(base64UrlEncode(ciphertext));
        protectedPayload.setWrappedContentKeys(wrapped);
        protectedPayload.setPayloadHash(sha256Hex(ciphertext));
        protectedPayload.setSignatureKid("");
        protectedPayload.setSignature("");
        return protectedPayload;
    }

    public static ProtectedPayload signProtectedPayload(
        Envelope envelope,
        ProtectedPayload protectedPayload,
        String signingPrivateKeyB64,
        String signatureKid
    ) {
        protectedPayload.setSignatureKid(signatureKid);
        byte[] signInput = messageSignatureInput(envelope, protectedPayload);
        protectedPayload.setSignature(signBytes(signInput, signingPrivateKeyB64));
        return protectedPayload;
    }

    public static boolean verifyProtectedPayloadSignature(
        Envelope envelope,
        ProtectedPayload protectedPayload,
        String senderSigningPublicKeyB64
    ) {
        if (protectedPayload.getSignature() == null || protectedPayload.getSignature().isBlank()) {
            return false;
        }
        return verifySignature(
            messageSignatureInput(envelope, protectedPayload),
            protectedPayload.getSignature(),
            senderSigningPublicKeyB64
        );
    }

    public static Map<String, Object> decryptForRecipient(
        Envelope envelope,
        ProtectedPayload protectedPayload,
        String recipientId,
        String recipientEncryptionPrivateKeyB64
    ) {
        WrappedContentKey match = protectedPayload.getWrappedContentKeys().stream()
            .filter(item -> recipientId.equals(item.getRecipient()))
            .findFirst()
            .orElseThrow(() -> new IllegalStateException("No wrapped content key for recipient " + recipientId));

        byte[] recipientPrivate = base64UrlDecode(recipientEncryptionPrivateKeyB64);
        X25519PrivateKeyParameters privateKey = new X25519PrivateKeyParameters(recipientPrivate, 0);
        byte[] ephemeralPublic = base64UrlDecode(match.getEphemeralPublicKey());
        byte[] sharedSecret = x25519SharedSecret(privateKey, ephemeralPublic);
        byte[] wrapKey = hkdfSha256(sharedSecret, ("acp-v1-wrap:" + recipientId).getBytes(StandardCharsets.UTF_8), 32);
        byte[] contentKey = aesGcmDecrypt(
            wrapKey,
            base64UrlDecode(match.getNonce()),
            base64UrlDecode(match.getCiphertext()),
            envelope.getMessageId().getBytes(StandardCharsets.UTF_8)
        );
        byte[] plaintext = aesGcmDecrypt(
            contentKey,
            base64UrlDecode(protectedPayload.getNonce()),
            base64UrlDecode(protectedPayload.getCiphertext()),
            envelopeAad(envelope)
        );
        return JsonSupport.mapFromJson(new String(plaintext, StandardCharsets.UTF_8));
    }

    public static String sha256Hex(byte[] value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value);
            StringBuilder builder = new StringBuilder(hash.length * 2);
            for (byte item : hash) {
                builder.append(String.format("%02x", item));
            }
            return builder.toString();
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to hash payload", exc);
        }
    }

    public static String base64UrlEncode(byte[] value) {
        return Base64.getUrlEncoder().encodeToString(value);
    }

    public static byte[] base64UrlDecode(String value) {
        return Base64.getUrlDecoder().decode(value);
    }

    private static byte[] messageSignatureInput(Envelope envelope, ProtectedPayload protectedPayload) {
        List<Map<String, Object>> sortedKeys = new ArrayList<>();
        protectedPayload.getWrappedContentKeys().stream()
            .sorted(Comparator.comparing(WrappedContentKey::getRecipient))
            .forEach(key -> sortedKeys.add(JsonSupport.toMap(key)));

        Map<String, Object> signableProtected = new HashMap<>();
        signableProtected.put("nonce", protectedPayload.getNonce());
        signableProtected.put("ciphertext", protectedPayload.getCiphertext());
        signableProtected.put("wrapped_content_keys", sortedKeys);
        signableProtected.put("payload_hash", protectedPayload.getPayloadHash());
        signableProtected.put("signature_kid", protectedPayload.getSignatureKid());

        Map<String, Object> body = new HashMap<>();
        body.put("envelope", envelope.toMap());
        body.put("protected", signableProtected);
        return CanonicalJson.bytes(body);
    }

    private static byte[] randomBytes(int length) {
        byte[] value = new byte[length];
        RANDOM.nextBytes(value);
        return value;
    }

    private static byte[] x25519SharedSecret(X25519PrivateKeyParameters privateKey, byte[] publicKeyRaw) {
        X25519PublicKeyParameters recipientPublic = new X25519PublicKeyParameters(publicKeyRaw, 0);
        X25519Agreement agreement = new X25519Agreement();
        agreement.init(privateKey);
        byte[] secret = new byte[agreement.getAgreementSize()];
        agreement.calculateAgreement(recipientPublic, secret, 0);
        return secret;
    }

    private static byte[] hkdfSha256(byte[] ikm, byte[] info, int length) {
        byte[] salt = new byte[32];
        byte[] prk = hmacSha256(salt, ikm);

        byte[] output = new byte[length];
        byte[] previous = new byte[0];
        int written = 0;
        int counter = 1;
        while (written < length) {
            byte[] message = new byte[previous.length + info.length + 1];
            System.arraycopy(previous, 0, message, 0, previous.length);
            System.arraycopy(info, 0, message, previous.length, info.length);
            message[message.length - 1] = (byte) counter;
            previous = hmacSha256(prk, message);
            int toWrite = Math.min(previous.length, length - written);
            System.arraycopy(previous, 0, output, written, toWrite);
            written += toWrite;
            counter += 1;
        }
        return output;
    }

    private static byte[] hmacSha256(byte[] key, byte[] data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to execute HMAC", exc);
        }
    }

    private static byte[] aesGcmEncrypt(byte[] key, byte[] nonce, byte[] plaintext, byte[] aad) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
            if (aad != null) {
                cipher.updateAAD(aad);
            }
            return cipher.doFinal(plaintext);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to encrypt AES-GCM payload", exc);
        }
    }

    private static byte[] aesGcmDecrypt(byte[] key, byte[] nonce, byte[] ciphertext, byte[] aad) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
            if (aad != null) {
                cipher.updateAAD(aad);
            }
            return cipher.doFinal(ciphertext);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to decrypt AES-GCM payload", exc);
        }
    }

    public record KeyMaterial(String privateKey, String publicKey) {
    }
}
