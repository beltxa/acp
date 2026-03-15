package org.acp.client;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import java.net.URI;
import java.net.http.HttpClient;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.time.Duration;

final class HttpSecurity {
    private HttpSecurity() {
    }

    static URI validateHttpUrl(String url, boolean allowInsecureHttp, String context) {
        URI uri = URI.create(url);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        if (!"http".equals(scheme) && !"https".equals(scheme)) {
            throw new IllegalStateException(context + " requires an http(s) URL, got: " + url);
        }
        if (uri.getHost() == null || uri.getHost().isBlank()) {
            throw new IllegalStateException(context + " URL is missing host: " + url);
        }
        if ("http".equals(scheme) && !allowInsecureHttp) {
            throw new IllegalStateException(
                context + " uses insecure HTTP (" + url + "). "
                    + "Set allowInsecureHttp=true only for local/dev/demo workflows."
            );
        }
        return uri;
    }

    static HttpClient buildHttpClient(int timeoutSeconds, boolean allowInsecureTls) {
        HttpClient.Builder builder = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(timeoutSeconds));
        if (allowInsecureTls) {
            try {
                builder.sslContext(insecureSslContext());
                SSLParameters params = new SSLParameters();
                params.setEndpointIdentificationAlgorithm("");
                builder.sslParameters(params);
            } catch (Exception exc) {
                throw new IllegalStateException("Unable to configure insecure TLS mode", exc);
            }
        }
        return builder.build();
    }

    private static SSLContext insecureSslContext() throws Exception {
        TrustManager[] trustAll = new TrustManager[]{
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
        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(null, trustAll, new SecureRandom());
        return sslContext;
    }
}
