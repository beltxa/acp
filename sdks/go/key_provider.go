package acp

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
)

type IdentityKeyMaterial struct {
	SigningPrivateKey    string
	EncryptionPrivateKey string
	SigningPublicKey     string
	EncryptionPublicKey  string
	SigningKID           string
	EncryptionKID        string
}

type TLSMaterial struct {
	CertFile string
	KeyFile  string
	CAFile   string
}

type KeyProvider interface {
	LoadIdentityKeys(agentID string) (*IdentityKeyMaterial, error)
	LoadTLSMaterial(agentID string) (*TLSMaterial, error)
	LoadCABundle(agentID string) (string, error)
	Describe() map[string]any
}

type LocalKeyProvider struct {
	storageDir string
	certFile   string
	keyFile    string
	caFile     string
}

func NewLocalKeyProvider(storageDir, certFile, keyFile, caFile string) *LocalKeyProvider {
	return &LocalKeyProvider{
		storageDir: storageDir,
		certFile:   strings.TrimSpace(certFile),
		keyFile:    strings.TrimSpace(keyFile),
		caFile:     strings.TrimSpace(caFile),
	}
}

func (provider *LocalKeyProvider) LoadIdentityKeys(agentID string) (*IdentityKeyMaterial, error) {
	bundle, err := ReadIdentity(provider.storageDir, agentID)
	if err != nil {
		return nil, err
	}
	if bundle == nil {
		return nil, KeyProviderError(fmt.Sprintf("Local identity not found for %s", agentID))
	}
	return &IdentityKeyMaterial{
		SigningPrivateKey:    bundle.Identity.SigningPrivateKey,
		EncryptionPrivateKey: bundle.Identity.EncryptionPrivateKey,
		SigningPublicKey:     bundle.Identity.SigningPublicKey,
		EncryptionPublicKey:  bundle.Identity.EncryptionPublicKey,
		SigningKID:           bundle.Identity.SigningKID,
		EncryptionKID:        bundle.Identity.EncryptionKID,
	}, nil
}

func (provider *LocalKeyProvider) LoadTLSMaterial(_ string) (*TLSMaterial, error) {
	return &TLSMaterial{
		CertFile: provider.certFile,
		KeyFile:  provider.keyFile,
		CAFile:   provider.caFile,
	}, nil
}

func (provider *LocalKeyProvider) LoadCABundle(_ string) (string, error) {
	return provider.caFile, nil
}

func (provider *LocalKeyProvider) Describe() map[string]any {
	return map[string]any{
		"provider":    "local",
		"storage_dir": provider.storageDir,
	}
}

type VaultKeyProvider struct {
	vaultURL          string
	vaultPath         string
	vaultTokenEnv     string
	vaultToken        string
	timeoutSeconds    int
	httpClient        *http.Client
	allowInsecureTLS  bool
	allowInsecureHTTP bool

	lock  sync.Mutex
	cache map[string]map[string]any
}

func NewVaultKeyProvider(
	vaultURL string,
	vaultPath string,
	vaultTokenEnv string,
	vaultToken string,
	timeoutSeconds int,
	caFile string,
	allowInsecureTLS bool,
	allowInsecureHTTP bool,
) (*VaultKeyProvider, error) {
	normalizedURL := strings.TrimSpace(vaultURL)
	normalizedPath := strings.TrimSpace(vaultPath)
	if normalizedURL == "" {
		return nil, KeyProviderError("vault_url is required for VaultKeyProvider")
	}
	if normalizedPath == "" {
		return nil, KeyProviderError("vault_path is required for VaultKeyProvider")
	}
	if _, err := ValidateHTTPURL(normalizedURL, allowInsecureHTTP, false, "Vault key provider URL"); err != nil {
		return nil, err
	}
	httpClient, err := BuildHTTPClient(HTTPSecurityPolicy{
		AllowInsecureHTTP: allowInsecureHTTP,
		AllowInsecureTLS:  allowInsecureTLS,
		MTLSEnabled:       false,
		CAFile:            caFile,
	}, timeoutSeconds)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(vaultTokenEnv) == "" {
		vaultTokenEnv = "VAULT_TOKEN"
	}
	return &VaultKeyProvider{
		vaultURL:          strings.TrimRight(normalizedURL, "/"),
		vaultPath:         strings.TrimPrefix(normalizedPath, "/"),
		vaultTokenEnv:     vaultTokenEnv,
		vaultToken:        strings.TrimSpace(vaultToken),
		timeoutSeconds:    maxInt(timeoutSeconds, 1),
		httpClient:        httpClient,
		allowInsecureTLS:  allowInsecureTLS,
		allowInsecureHTTP: allowInsecureHTTP,
		cache:             map[string]map[string]any{},
	}, nil
}

func (provider *VaultKeyProvider) Describe() map[string]any {
	return map[string]any{
		"provider":        "vault",
		"vault_url":       provider.vaultURL,
		"vault_path":      provider.vaultPath,
		"vault_token_env": provider.vaultTokenEnv,
	}
}

func (provider *VaultKeyProvider) resolveToken() string {
	if provider.vaultToken != "" {
		return provider.vaultToken
	}
	return strings.TrimSpace(os.Getenv(provider.vaultTokenEnv))
}

func (provider *VaultKeyProvider) secretPath(agentID string) string {
	sanitized := SanitizeAgentID(agentID)
	if strings.Contains(provider.vaultPath, "{agent_id}") {
		return strings.ReplaceAll(provider.vaultPath, "{agent_id}", sanitized)
	}
	return strings.TrimRight(provider.vaultPath, "/") + "/" + sanitized
}

func (provider *VaultKeyProvider) loadSecret(agentID string) (map[string]any, error) {
	path := provider.secretPath(agentID)
	provider.lock.Lock()
	cached, ok := provider.cache[path]
	provider.lock.Unlock()
	if ok {
		return cached, nil
	}
	token := provider.resolveToken()
	if token == "" {
		return nil, KeyProviderError(fmt.Sprintf("Vault token is missing. Set token or environment variable %s.", provider.vaultTokenEnv))
	}
	request, err := http.NewRequest(http.MethodGet, provider.vaultURL+"/v1/"+strings.TrimPrefix(path, "/"), nil)
	if err != nil {
		return nil, KeyProviderError(fmt.Sprintf("unable to build Vault request: %v", err))
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("X-Vault-Token", token)
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return nil, KeyProviderError(fmt.Sprintf("Vault request failed for path %s: %v", path, err))
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, KeyProviderError(fmt.Sprintf("Vault returned HTTP %d for path %s", response.StatusCode, path))
	}
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, KeyProviderError(fmt.Sprintf("unable to read Vault response: %v", err))
	}
	var parsed map[string]any
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, KeyProviderError(fmt.Sprintf("unable to parse Vault response: %v", err))
	}
	dataRaw, ok := parsed["data"].(map[string]any)
	if !ok {
		return nil, KeyProviderError(fmt.Sprintf("Vault response for path %s is missing data object", path))
	}
	secret := dataRaw
	if nestedRaw, ok := dataRaw["data"].(map[string]any); ok {
		secret = nestedRaw
	}
	provider.lock.Lock()
	provider.cache[path] = secret
	provider.lock.Unlock()
	return secret, nil
}

func (provider *VaultKeyProvider) LoadIdentityKeys(agentID string) (*IdentityKeyMaterial, error) {
	secret, err := provider.loadSecret(agentID)
	if err != nil {
		return nil, err
	}
	signingPrivateKey := secretValue(secret, "signing_key", "identity_signing_key", "signing_private_key")
	encryptionPrivateKey := secretValue(secret, "encryption_key", "identity_encryption_key", "encryption_private_key")
	if signingPrivateKey == "" {
		return nil, KeyProviderError(fmt.Sprintf("Vault secret for %s is missing signing_key", agentID))
	}
	if encryptionPrivateKey == "" {
		return nil, KeyProviderError(fmt.Sprintf("Vault secret for %s is missing encryption_key", agentID))
	}
	return &IdentityKeyMaterial{
		SigningPrivateKey:    signingPrivateKey,
		EncryptionPrivateKey: encryptionPrivateKey,
		SigningPublicKey:     secretValue(secret, "signing_public_key"),
		EncryptionPublicKey:  secretValue(secret, "encryption_public_key"),
		SigningKID:           secretValue(secret, "signing_kid"),
		EncryptionKID:        secretValue(secret, "encryption_kid"),
	}, nil
}

func (provider *VaultKeyProvider) LoadTLSMaterial(agentID string) (*TLSMaterial, error) {
	secret, err := provider.loadSecret(agentID)
	if err != nil {
		return nil, err
	}
	return &TLSMaterial{
		CertFile: secretValue(secret, "tls_cert_file", "tls_cert", "cert_file"),
		KeyFile:  secretValue(secret, "tls_key_file", "tls_key", "key_file"),
		CAFile:   secretValue(secret, "ca_bundle_file", "ca_file", "ca_bundle"),
	}, nil
}

func (provider *VaultKeyProvider) LoadCABundle(agentID string) (string, error) {
	secret, err := provider.loadSecret(agentID)
	if err != nil {
		return "", err
	}
	return secretValue(secret, "ca_bundle_file", "ca_file", "ca_bundle"), nil
}

func secretValue(secret map[string]any, keys ...string) string {
	for _, key := range keys {
		value, ok := secret[key].(string)
		if !ok {
			continue
		}
		normalized := strings.TrimSpace(value)
		if normalized != "" {
			return normalized
		}
	}
	return ""
}
