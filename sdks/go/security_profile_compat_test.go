package acp

import (
	"path/filepath"
	"testing"
)

func securityVectorsDir(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "tests", "vectors", "security")
}

func TestReadsSharedSecurityHTTPSFixtureWithExpectedSchema(t *testing.T) {
	fixture := loadJSONFixtureMap(t, filepath.Join(securityVectorsDir(t), "security_profile_https.json"))
	options := OptionsFromConfigMap(fixture)
	if options.KeyProvider != "vault" {
		t.Fatalf("key_provider mismatch: %s", options.KeyProvider)
	}
	if options.VaultURL != "https://vault.company.net" {
		t.Fatalf("vault_url mismatch: %s", options.VaultURL)
	}
	if options.VaultPath != "secret/data/acp/identities" {
		t.Fatalf("vault_path mismatch: %s", options.VaultPath)
	}
	if options.VaultTokenEnv != "VAULT_TOKEN" {
		t.Fatalf("vault_token_env mismatch: %s", options.VaultTokenEnv)
	}
	if options.AllowInsecureHTTP {
		t.Fatalf("allow_insecure_http must be false")
	}
	if options.AllowInsecureTLS {
		t.Fatalf("allow_insecure_tls must be false")
	}
	if options.MTLSEnabled {
		t.Fatalf("mtls_enabled must be false")
	}
}

func TestReadsSharedSecurityVaultMTLSFixtureWithProviderBackedMaterial(t *testing.T) {
	fixture := loadJSONFixtureMap(t, filepath.Join(securityVectorsDir(t), "security_profile_vault_mtls.json"))
	options := OptionsFromConfigMap(fixture)
	if options.KeyProvider != "vault" {
		t.Fatalf("key_provider mismatch: %s", options.KeyProvider)
	}
	if !options.MTLSEnabled {
		t.Fatalf("mtls_enabled must be true")
	}
	if options.CAFile != "/etc/acp/ca/security-profile-ca.pem" {
		t.Fatalf("ca_file mismatch: %s", options.CAFile)
	}
	if options.CertFile != "" {
		t.Fatalf("cert_file should remain empty for provider-backed cert material")
	}
	if options.KeyFile != "" {
		t.Fatalf("key_file should remain empty for provider-backed key material")
	}
}

func TestToConfigMapExportsAlignedSecurityFields(t *testing.T) {
	options := DefaultAgentOptions()
	options.KeyProvider = "vault"
	options.VaultURL = "https://vault.company.net"
	options.VaultPath = "secret/data/acp/identities"
	options.VaultTokenEnv = "VAULT_TOKEN"
	options.AllowInsecureHTTP = false
	options.AllowInsecureTLS = false
	options.MTLSEnabled = true
	options.CAFile = "/etc/acp/ca/security-profile-ca.pem"
	exported := options.ToConfigMap()

	if exported["key_provider"] != "vault" {
		t.Fatalf("key_provider export mismatch")
	}
	if exported["vault_url"] != "https://vault.company.net" {
		t.Fatalf("vault_url export mismatch")
	}
	if exported["vault_path"] != "secret/data/acp/identities" {
		t.Fatalf("vault_path export mismatch")
	}
	if exported["vault_token_env"] != "VAULT_TOKEN" {
		t.Fatalf("vault_token_env export mismatch")
	}
	if exported["allow_insecure_http"] != false {
		t.Fatalf("allow_insecure_http export mismatch")
	}
	if exported["allow_insecure_tls"] != false {
		t.Fatalf("allow_insecure_tls export mismatch")
	}
	if exported["mtls_enabled"] != true {
		t.Fatalf("mtls_enabled export mismatch")
	}
	if exported["ca_file"] != "/etc/acp/ca/security-profile-ca.pem" {
		t.Fatalf("ca_file export mismatch")
	}
}

func TestFromConfigMapPreservesDefaultProviderValuesWhenUnset(t *testing.T) {
	options := OptionsFromConfigMap(map[string]any{})
	if options.KeyProvider != "local" {
		t.Fatalf("default key_provider mismatch")
	}
	if options.VaultTokenEnv != "VAULT_TOKEN" {
		t.Fatalf("default vault_token_env mismatch")
	}
}
