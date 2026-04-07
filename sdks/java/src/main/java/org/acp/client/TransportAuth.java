/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import org.bouncycastle.asn1.pkcs.PrivateKeyInfo;
import org.bouncycastle.openssl.PEMKeyPair;
import org.bouncycastle.openssl.PEMParser;
import org.bouncycastle.openssl.jcajce.JcaPEMKeyConverter;

import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class TransportAuth {
    static final Set<String> SUPPORTED_AUTH_TYPES = Set.of(
        "none",
        "bearer",
        "basic",
        "mtls",
        "username_password",
        "custom"
    );

    private TransportAuth() {
    }

    static String normalizeAuthType(String value) {
        String normalized = value == null ? "" : value.trim().toLowerCase();
        if (normalized.isEmpty()) {
            normalized = "none";
        }
        if (!SUPPORTED_AUTH_TYPES.contains(normalized)) {
            throw new IllegalStateException("Unsupported auth type: " + value);
        }
        return normalized;
    }

    static AuthConfig normalizeAuthConfig(AuthConfig auth) {
        if (auth == null) {
            return null;
        }
        String type = normalizeAuthType(auth.getType());
        Map<String, String> parameters = new LinkedHashMap<>();
        if (auth.getParameters() != null) {
            for (Map.Entry<String, String> entry : auth.getParameters().entrySet()) {
                if (entry.getKey() == null) {
                    continue;
                }
                String key = entry.getKey().trim();
                if (key.isEmpty()) {
                    continue;
                }
                String value = entry.getValue() == null ? "" : entry.getValue().trim();
                parameters.put(key, value);
            }
        }
        return new AuthConfig(type, parameters);
    }

    static AuthConfig parseAuthConfig(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof AuthConfig auth) {
            return normalizeAuthConfig(auth);
        }
        if (!(value instanceof Map<?, ?> raw)) {
            throw new IllegalStateException("Transport auth must be an object with fields: type, parameters");
        }
        String type = raw.get("type") instanceof String str ? str : "none";
        Map<String, String> parameters = new LinkedHashMap<>();
        Object rawParameters = raw.get("parameters");
        if (rawParameters != null) {
            if (!(rawParameters instanceof Map<?, ?> map)) {
                throw new IllegalStateException("Transport auth.parameters must be an object");
            }
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (entry.getKey() == null || entry.getValue() == null) {
                    continue;
                }
                parameters.put(String.valueOf(entry.getKey()), String.valueOf(entry.getValue()));
            }
        }
        return normalizeAuthConfig(new AuthConfig(type, parameters));
    }

    static AuthConfig parseAuthFromService(Map<String, Object> service) {
        if (service == null) {
            return null;
        }
        return parseAuthConfig(service.get("auth"));
    }

    static void assertAllowedAuthTypes(AuthConfig auth, Set<String> allowed, String context) {
        if (auth == null) {
            return;
        }
        if (allowed.contains(auth.getType())) {
            return;
        }
        throw new IllegalStateException(context + " does not support auth type: " + auth.getType());
    }

    static String requireParameter(AuthConfig auth, String key, String context) {
        if (auth == null) {
            throw new IllegalStateException(context + " requires auth.parameters." + key);
        }
        String value = optionalParameter(auth, key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(context + " requires auth.parameters." + key);
        }
        return value;
    }

    static String optionalParameter(AuthConfig auth, String key) {
        if (auth == null || auth.getParameters() == null) {
            return null;
        }
        String value = auth.getParameters().get(key);
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    static Map<String, Object> serializeAuthConfig(AuthConfig auth) {
        AuthConfig normalized = normalizeAuthConfig(auth);
        if (normalized == null) {
            return null;
        }
        Map<String, Object> parameters = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : normalized.getParameters().entrySet()) {
            parameters.put(entry.getKey(), entry.getValue());
        }
        Map<String, Object> serialized = new LinkedHashMap<>();
        serialized.put("type", normalized.getType());
        serialized.put("parameters", parameters);
        return serialized;
    }

    static Map<String, String> httpAuthHeaders(AuthConfig auth) {
        Map<String, String> headers = new LinkedHashMap<>();
        if (auth == null || "none".equals(auth.getType()) || "mtls".equals(auth.getType())) {
            return headers;
        }
        if ("bearer".equals(auth.getType())) {
            String token = requireParameter(auth, "token", "Bearer auth");
            headers.put("Authorization", "Bearer " + token);
            return headers;
        }
        if ("basic".equals(auth.getType())) {
            String username = requireParameter(auth, "username", "Basic auth");
            String password = requireParameter(auth, "password", "Basic auth");
            String encoded = Base64.getEncoder().encodeToString(
                (username + ":" + password).getBytes(StandardCharsets.UTF_8)
            );
            headers.put("Authorization", "Basic " + encoded);
            return headers;
        }
        if ("custom".equals(auth.getType())) {
            String header = optionalParameter(auth, "header");
            String value = optionalParameter(auth, "value");
            String scheme = optionalParameter(auth, "scheme");
            if (header != null) {
                if (value == null) {
                    throw new IllegalStateException("Custom auth requires auth.parameters.value when header is set");
                }
                headers.put(header, value);
                return headers;
            }
            if (scheme != null) {
                if (value == null) {
                    throw new IllegalStateException("Custom auth requires auth.parameters.value when scheme is set");
                }
                headers.put("Authorization", scheme + " " + value);
                return headers;
            }
            throw new IllegalStateException(
                "Custom auth requires either parameters.header + parameters.value or parameters.scheme + parameters.value"
            );
        }
        throw new IllegalStateException("HTTP/relay transport does not support auth type: " + auth.getType());
    }

    static SSLContext sslContextFromAuth(AuthConfig auth, boolean requireClientCertificate, String context) {
        if (auth == null) {
            return null;
        }
        String certPath = optionalParameter(auth, "cert_path");
        String keyPath = optionalParameter(auth, "key_path");
        String caPath = optionalParameter(auth, "ca_path");
        if (requireClientCertificate && (certPath == null || keyPath == null)) {
            throw new IllegalStateException(context + " requires auth.parameters.cert_path and auth.parameters.key_path");
        }
        if ((certPath == null) != (keyPath == null)) {
            throw new IllegalStateException(context + " requires both auth.parameters.cert_path and auth.parameters.key_path when either is configured");
        }
        if (certPath == null && keyPath == null && caPath == null) {
            return null;
        }
        try {
            TrustManager[] trustManagers = caPath == null ? null : trustManagersFromCa(Path.of(caPath));
            KeyManager[] keyManagers = certPath == null
                ? null
                : keyManagersFromClientCertificate(Path.of(certPath), Path.of(keyPath));
            SSLContext sslContext = SSLContext.getInstance("TLS");
            sslContext.init(keyManagers, trustManagers, new SecureRandom());
            return sslContext;
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to configure " + context + " TLS context", exc);
        }
    }

    private static TrustManager[] trustManagersFromCa(Path caPath) throws Exception {
        List<X509Certificate> certificates = loadCertificates(caPath);
        if (certificates.isEmpty()) {
            throw new IllegalStateException("No CA certificates found in " + caPath);
        }
        KeyStore trustStore = KeyStore.getInstance(KeyStore.getDefaultType());
        trustStore.load(null, null);
        for (int i = 0; i < certificates.size(); i++) {
            trustStore.setCertificateEntry("ca-" + i, certificates.get(i));
        }
        TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        trustManagerFactory.init(trustStore);
        return trustManagerFactory.getTrustManagers();
    }

    private static KeyManager[] keyManagersFromClientCertificate(Path certPath, Path keyPath) throws Exception {
        List<X509Certificate> certificateChain = loadCertificates(certPath);
        if (certificateChain.isEmpty()) {
            throw new IllegalStateException("No client certificate found in " + certPath);
        }
        PrivateKey privateKey = loadPrivateKey(keyPath);
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        char[] password = "acp-client".toCharArray();
        keyStore.load(null, password);
        keyStore.setKeyEntry(
            "acp-client",
            privateKey,
            password,
            certificateChain.toArray(new Certificate[0])
        );
        KeyManagerFactory keyManagerFactory = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm()
        );
        keyManagerFactory.init(keyStore, password);
        return keyManagerFactory.getKeyManagers();
    }

    private static List<X509Certificate> loadCertificates(Path path) throws Exception {
        CertificateFactory certificateFactory = CertificateFactory.getInstance("X.509");
        try (var input = Files.newInputStream(path)) {
            return certificateFactory
                .generateCertificates(input)
                .stream()
                .map(certificate -> (X509Certificate) certificate)
                .toList();
        }
    }

    private static PrivateKey loadPrivateKey(Path keyPath) throws Exception {
        try (Reader reader = Files.newBufferedReader(keyPath); PEMParser parser = new PEMParser(reader)) {
            Object parsed = parser.readObject();
            if (parsed == null) {
                throw new IllegalStateException("Private key file is empty: " + keyPath);
            }
            JcaPEMKeyConverter converter = new JcaPEMKeyConverter();
            if (parsed instanceof PEMKeyPair keyPair) {
                return converter.getKeyPair(keyPair).getPrivate();
            }
            if (parsed instanceof PrivateKeyInfo privateKeyInfo) {
                return converter.getPrivateKey(privateKeyInfo);
            }
            throw new IllegalStateException("Unsupported private key format in " + keyPath);
        }
    }
}
