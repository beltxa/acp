package org.acp.client;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SecurityProfileConfigCompatibilityTest {
    @Test
    void readsSharedSecurityHttpsFixtureWithExpectedSchema() throws Exception {
        Map<String, Object> fixture = readFixture("security_profile_https.json");
        AcpAgentOptions options = AcpAgentOptions.fromConfigMap(fixture);
        assertEquals("vault", options.getKeyProvider());
        assertEquals("https://vault.company.net", options.getVaultUrl());
        assertEquals("secret/data/acp/identities", options.getVaultPath());
        assertEquals("VAULT_TOKEN", options.getVaultTokenEnv());
        assertFalse(options.isAllowInsecureHttp());
        assertFalse(options.isAllowInsecureTls());
        assertFalse(options.isMtlsEnabled());
    }

    @Test
    void readsSharedSecurityVaultMtlsFixtureWithProviderBackedMaterial() throws Exception {
        Map<String, Object> fixture = readFixture("security_profile_vault_mtls.json");
        AcpAgentOptions options = AcpAgentOptions.fromConfigMap(fixture);
        assertEquals("vault", options.getKeyProvider());
        assertTrue(options.isMtlsEnabled());
        assertEquals("/etc/acp/ca/security-profile-ca.pem", options.getCaFile());
        org.junit.jupiter.api.Assertions.assertNull(options.getCertFile());
        org.junit.jupiter.api.Assertions.assertNull(options.getKeyFile());
    }

    @Test
    void toConfigMapExportsAlignedSecurityFields() {
        AcpAgentOptions options = new AcpAgentOptions()
            .setKeyProvider("vault")
            .setVaultUrl("https://vault.company.net")
            .setVaultPath("secret/data/acp/identities")
            .setVaultTokenEnv("VAULT_TOKEN")
            .setAllowInsecureHttp(false)
            .setAllowInsecureTls(false)
            .setMtlsEnabled(true)
            .setCaFile("/etc/acp/ca/security-profile-ca.pem");
        Map<String, Object> exported = options.toConfigMap();
        assertEquals("vault", exported.get("key_provider"));
        assertEquals("https://vault.company.net", exported.get("vault_url"));
        assertEquals("secret/data/acp/identities", exported.get("vault_path"));
        assertEquals("VAULT_TOKEN", exported.get("vault_token_env"));
        assertEquals(Boolean.FALSE, exported.get("allow_insecure_http"));
        assertEquals(Boolean.FALSE, exported.get("allow_insecure_tls"));
        assertEquals(Boolean.TRUE, exported.get("mtls_enabled"));
        assertEquals("/etc/acp/ca/security-profile-ca.pem", exported.get("ca_file"));
    }

    @Test
    void fromConfigMapPreservesDefaultProviderValuesWhenUnset() {
        AcpAgentOptions options = AcpAgentOptions.fromConfigMap(Map.of());
        assertEquals("local", options.getKeyProvider());
        assertEquals("VAULT_TOKEN", options.getVaultTokenEnv());
    }

    private static Map<String, Object> readFixture(String name) throws Exception {
        Path fixture = Path.of("..", "tests", "vectors", "security", name);
        return JsonSupport.mapFromJson(Files.readString(fixture));
    }
}
