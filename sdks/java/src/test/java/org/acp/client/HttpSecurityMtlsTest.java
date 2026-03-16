package org.acp.client;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HttpSecurityMtlsTest {
    @Test
    void validatesCustomCaFileConfiguration() {
        Path caPath = resourcePath("tls/test-ca.pem");
        assertDoesNotThrow(() -> HttpSecurity.validateHttpClientPolicy(
            false,
            caPath.toString(),
            false,
            null,
            null,
            "test policy"
        ));
    }

    @Test
    void rejectsMissingClientCertificateWhenMtlsEnabled() {
        IllegalStateException exc = assertThrows(
            IllegalStateException.class,
            () -> HttpSecurity.validateHttpClientPolicy(
                false,
                null,
                true,
                null,
                null,
                "test policy"
            )
        );
        org.junit.jupiter.api.Assertions.assertTrue(exc.getMessage().contains("certFile"));
    }

    @Test
    void rejectsHttpUrlWhenMtlsEnabled() {
        IllegalStateException exc = assertThrows(
            IllegalStateException.class,
            () -> HttpSecurity.validateHttpUrl(
                "http://localhost:8443/acp/inbox",
                true,
                true,
                "test URL"
            )
        );
        org.junit.jupiter.api.Assertions.assertTrue(exc.getMessage().contains("mtlsEnabled=true"));
    }

    @Test
    void buildsHttpClientWithMtlsMaterial() {
        Path caPath = resourcePath("tls/test-ca.pem");
        Path certPath = resourcePath("tls/test-client-cert.pem");
        Path keyPath = resourcePath("tls/test-client-key.pem");
        assertDoesNotThrow(() -> {
            var client = HttpSecurity.buildHttpClient(
                5,
                false,
                caPath.toString(),
                true,
                certPath.toString(),
                keyPath.toString()
            );
            assertNotNull(client);
        });
    }

    private static Path resourcePath(String resource) {
        try {
            return Path.of(
                HttpSecurityMtlsTest.class.getClassLoader().getResource(resource).toURI()
            );
        } catch (Exception exc) {
            throw new IllegalStateException("Missing test resource: " + resource, exc);
        }
    }
}
