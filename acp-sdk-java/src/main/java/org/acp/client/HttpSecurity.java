package org.acp.client;

import org.bouncycastle.asn1.pkcs.PrivateKeyInfo;
import org.bouncycastle.openssl.PEMKeyPair;
import org.bouncycastle.openssl.PEMParser;
import org.bouncycastle.openssl.jcajce.JcaPEMKeyConverter;

import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;
import java.io.Reader;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

final class HttpSecurity {
    private HttpSecurity() {
    }

    static URI validateHttpUrl(String url, boolean allowInsecureHttp, boolean mtlsEnabled, String context) {
        URI uri = URI.create(url);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        if (!"http".equals(scheme) && !"https".equals(scheme)) {
            throw new IllegalStateException(context + " requires an http(s) URL, got: " + url);
        }
        if (uri.getHost() == null || uri.getHost().isBlank()) {
            throw new IllegalStateException(context + " URL is missing host: " + url);
        }
        if ("http".equals(scheme) && mtlsEnabled) {
            throw new IllegalStateException(
                context + " cannot use HTTP (" + url + ") when mtlsEnabled=true. Use https:// endpoints."
            );
        }
        if ("http".equals(scheme) && !allowInsecureHttp) {
            throw new IllegalStateException(
                context + " uses insecure HTTP (" + url + "). "
                    + "Set allowInsecureHttp=true only for local/dev/demo workflows."
            );
        }
        return uri;
    }

    static void validateHttpClientPolicy(
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile,
        String context
    ) {
        String normalizedCa = normalizeFile(caFile, context, "caFile");
        String normalizedCert = normalizeFile(certFile, context, "certFile");
        String normalizedKey = normalizeFile(keyFile, context, "keyFile");
        if (mtlsEnabled) {
            if (normalizedCert == null) {
                throw new IllegalStateException(context + " requires certFile when mtlsEnabled=true");
            }
            if (normalizedKey == null) {
                throw new IllegalStateException(context + " requires keyFile when mtlsEnabled=true");
            }
        } else if ((normalizedCert == null) != (normalizedKey == null)) {
            throw new IllegalStateException(context + " requires both certFile and keyFile when either is configured");
        }
        if (allowInsecureTls && normalizedCa != null) {
            // keep behavior deterministic: CA will be ignored while TLS verification is disabled
        }
    }

    static HttpClient buildHttpClient(
        int timeoutSeconds,
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile
    ) {
        validateHttpClientPolicy(
            allowInsecureTls,
            caFile,
            mtlsEnabled,
            certFile,
            keyFile,
            "HTTP client configuration"
        );

        HttpClient.Builder builder = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(timeoutSeconds));

        try {
            SSLContext sslContext = buildSslContext(
                allowInsecureTls,
                caFile,
                mtlsEnabled,
                certFile,
                keyFile
            );
            if (sslContext != null) {
                builder.sslContext(sslContext);
            }
            if (allowInsecureTls) {
                SSLParameters params = new SSLParameters();
                params.setEndpointIdentificationAlgorithm("");
                builder.sslParameters(params);
            }
            return builder.build();
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to configure HTTP TLS context", exc);
        }
    }

    private static SSLContext buildSslContext(
        boolean allowInsecureTls,
        String caFile,
        boolean mtlsEnabled,
        String certFile,
        String keyFile
    ) throws Exception {
        boolean hasCustomCa = normalizeFile(caFile, "HTTP client configuration", "caFile") != null;
        boolean hasClientCertificate = mtlsEnabled;
        if (!allowInsecureTls && !hasCustomCa && !hasClientCertificate) {
            return null;
        }

        TrustManager[] trustManagers = null;
        if (allowInsecureTls) {
            trustManagers = insecureTrustManagers();
        } else if (hasCustomCa) {
            trustManagers = trustManagersFromCa(Path.of(caFile));
        }

        KeyManager[] keyManagers = null;
        if (hasClientCertificate) {
            keyManagers = keyManagersFromClientCertificate(Path.of(certFile), Path.of(keyFile));
        }

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(keyManagers, trustManagers, new SecureRandom());
        return sslContext;
    }

    private static String normalizeFile(String value, String context, String label) {
        if (value == null || value.isBlank()) {
            return null;
        }
        Path path = Path.of(value);
        if (!Files.isRegularFile(path)) {
            throw new IllegalStateException(context + " " + label + " does not exist or is not a file: " + value);
        }
        return value;
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
        List<X509Certificate> certificates = new ArrayList<>();
        try (var input = Files.newInputStream(path)) {
            for (Certificate certificate : certificateFactory.generateCertificates(input)) {
                certificates.add((X509Certificate) certificate);
            }
        }
        return certificates;
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

    private static TrustManager[] insecureTrustManagers() {
        return new TrustManager[]{
            new X509TrustManager() {
                @Override
                public void checkClientTrusted(X509Certificate[] chain, String authType) {
                }

                @Override
                public void checkServerTrusted(X509Certificate[] chain, String authType) {
                }

                @Override
                public X509Certificate[] getAcceptedIssuers() {
                    return new X509Certificate[0];
                }
            },
        };
    }
}
