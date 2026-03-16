package acp

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
)

type AgentIdentity struct {
	AgentID              string `json:"agent_id"`
	SigningPrivateKey    string `json:"signing_private_key"`
	SigningPublicKey     string `json:"signing_public_key"`
	EncryptionPrivateKey string `json:"encryption_private_key"`
	EncryptionPublicKey  string `json:"encryption_public_key"`
	SigningKID           string `json:"signing_kid"`
	EncryptionKID        string `json:"encryption_kid"`
}

type AgentIDParts struct {
	Name   string
	Domain string
}

type IdentityBundle struct {
	Identity         AgentIdentity
	IdentityDocument map[string]any
}

type ProviderIdentityInput struct {
	AgentID              string
	SigningPrivateKey    string
	EncryptionPrivateKey string
	SigningPublicKey     string
	EncryptionPublicKey  string
	SigningKID           string
	EncryptionKID        string
}

const (
	identityFileName    = "identity.json"
	identityDocFileName = "identity_document.json"
)

var agentIDPattern = regexp.MustCompile(`^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$`)

func ParseAgentID(agentID string) (AgentIDParts, error) {
	matches := agentIDPattern.FindStringSubmatch(agentID)
	if len(matches) == 0 {
		return AgentIDParts{}, ValidationError(fmt.Sprintf("Invalid agent identifier: %s", agentID))
	}
	parts := AgentIDParts{}
	for index, name := range agentIDPattern.SubexpNames() {
		switch name {
		case "name":
			parts.Name = matches[index]
		case "domain":
			parts.Domain = matches[index]
		}
	}
	if strings.TrimSpace(parts.Name) == "" {
		return AgentIDParts{}, ValidationError(fmt.Sprintf("Invalid agent identifier: %s", agentID))
	}
	return parts, nil
}

func SanitizeAgentID(agentID string) string {
	var out strings.Builder
	for _, char := range agentID {
		if (char >= 'a' && char <= 'z') ||
			(char >= 'A' && char <= 'Z') ||
			(char >= '0' && char <= '9') ||
			char == '.' || char == '_' || char == '-' {
			out.WriteRune(char)
			continue
		}
		out.WriteRune('_')
	}
	return out.String()
}

func identityPath(storageDir string, agentID string) string {
	return filepath.Join(storageDir, SanitizeAgentID(agentID))
}

func CreateIdentity(agentID string) (AgentIdentity, error) {
	if _, err := ParseAgentID(agentID); err != nil {
		return AgentIdentity{}, err
	}
	signingPrivateKey, signingPublicKey, err := GenerateEd25519Keypair()
	if err != nil {
		return AgentIdentity{}, err
	}
	encryptionPrivateKey, encryptionPublicKey, err := GenerateX25519Keypair()
	if err != nil {
		return AgentIdentity{}, err
	}
	return AgentIdentity{
		AgentID:              agentID,
		SigningPrivateKey:    signingPrivateKey,
		SigningPublicKey:     signingPublicKey,
		EncryptionPrivateKey: encryptionPrivateKey,
		EncryptionPublicKey:  encryptionPublicKey,
		SigningKID:           "sig-" + strings.ReplaceAll(uuid.NewString(), "-", "")[:12],
		EncryptionKID:        "enc-" + strings.ReplaceAll(uuid.NewString(), "-", "")[:12],
	}, nil
}

type BuildIdentityDocumentInput struct {
	Identity             AgentIdentity
	DirectEndpoint       string
	RelayHints           []string
	TrustProfile         string
	Capabilities         map[string]any
	ValidDays            int
	AMQPService          map[string]any
	MQTTService          map[string]any
	HTTPSecurityProfile  string
	RelaySecurityProfile string
}

func BuildIdentityDocument(input BuildIdentityDocumentInput) (map[string]any, error) {
	if !IsSupportedTrustProfile(input.TrustProfile) {
		return nil, ValidationError(fmt.Sprintf("Unsupported trust profile: %s", input.TrustProfile))
	}
	now := time.Now().UTC()
	validUntil := now.Add(time.Duration(maxInt(input.ValidDays, 1)) * 24 * time.Hour)
	service := map[string]any{
		"direct_endpoint": nullableString(input.DirectEndpoint),
		"relay_hints":     append([]string{}, input.RelayHints...),
	}
	if input.AMQPService != nil {
		service["amqp"] = input.AMQPService
	}
	if input.MQTTService != nil {
		service["mqtt"] = input.MQTTService
	}
	if strings.TrimSpace(input.DirectEndpoint) != "" && strings.TrimSpace(input.HTTPSecurityProfile) != "" {
		service["http"] = map[string]any{
			"endpoint":         strings.TrimSpace(input.DirectEndpoint),
			"security_profile": strings.TrimSpace(input.HTTPSecurityProfile),
		}
	}
	if len(input.RelayHints) > 0 && strings.TrimSpace(input.RelaySecurityProfile) != "" {
		service["relay"] = map[string]any{
			"endpoint":         strings.TrimSpace(input.RelayHints[0]),
			"security_profile": strings.TrimSpace(input.RelaySecurityProfile),
		}
	}
	document := map[string]any{
		"acp_identity_version": ACPIdentityVersion,
		"agent_id":             input.Identity.AgentID,
		"created_at":           now.Format(time.RFC3339),
		"valid_until":          validUntil.Format(time.RFC3339),
		"trust_profile":        input.TrustProfile,
		"keys": map[string]any{
			"signing": map[string]any{
				"kid":        input.Identity.SigningKID,
				"alg":        "Ed25519",
				"public_key": input.Identity.SigningPublicKey,
			},
			"encryption": map[string]any{
				"kid":        input.Identity.EncryptionKID,
				"alg":        "X25519",
				"public_key": input.Identity.EncryptionPublicKey,
			},
		},
		"service":      service,
		"capabilities": mapOrDefault(input.Capabilities),
	}
	signatureInput, err := CanonicalJSONBytes(document)
	if err != nil {
		return nil, err
	}
	signatureValue, err := SignBytes(signatureInput, input.Identity.SigningPrivateKey)
	if err != nil {
		return nil, err
	}
	document["signature"] = map[string]any{
		"algorithm": "Ed25519",
		"signed_by": input.Identity.SigningKID,
		"value":     signatureValue,
	}
	return document, nil
}

func VerifyIdentityDocument(identityDocument map[string]any) bool {
	requiredFields := []string{"agent_id", "keys", "service", "signature", "valid_until"}
	for _, field := range requiredFields {
		if _, ok := identityDocument[field]; !ok {
			return false
		}
	}
	trustProfile, ok := identityDocument["trust_profile"].(string)
	if !ok || !IsSupportedTrustProfile(trustProfile) {
		return false
	}
	validUntilRaw, ok := identityDocument["valid_until"].(string)
	if !ok {
		return false
	}
	validUntil, err := time.Parse(time.RFC3339, validUntilRaw)
	if err != nil || !validUntil.After(time.Now().UTC()) {
		return false
	}
	keys, ok := identityDocument["keys"].(map[string]any)
	if !ok {
		return false
	}
	signing, ok := keys["signing"].(map[string]any)
	if !ok {
		return false
	}
	signingPublicKey, ok := signing["public_key"].(string)
	if !ok || strings.TrimSpace(signingPublicKey) == "" {
		return false
	}
	signature, ok := identityDocument["signature"].(map[string]any)
	if !ok {
		return false
	}
	signatureValue, ok := signature["value"].(string)
	if !ok || strings.TrimSpace(signatureValue) == "" {
		return false
	}
	unsigned := copyMap(identityDocument)
	delete(unsigned, "signature")
	signatureInput, err := CanonicalJSONBytes(unsigned)
	if err != nil {
		return false
	}
	return VerifySignature(signatureInput, signatureValue, signingPublicKey)
}

func WriteIdentity(storageDir string, identity AgentIdentity, identityDocument map[string]any) error {
	path := identityPath(storageDir, identity.AgentID)
	if err := os.MkdirAll(path, 0o755); err != nil {
		return ValidationError(fmt.Sprintf("unable to create identity directory: %v", err))
	}
	identityBytes, err := json.MarshalIndent(identity, "", "  ")
	if err != nil {
		return ValidationError(fmt.Sprintf("unable to serialize identity: %v", err))
	}
	if err := os.WriteFile(filepath.Join(path, identityFileName), identityBytes, 0o600); err != nil {
		return ValidationError(fmt.Sprintf("unable to persist identity: %v", err))
	}
	documentBytes, err := json.MarshalIndent(identityDocument, "", "  ")
	if err != nil {
		return ValidationError(fmt.Sprintf("unable to serialize identity document: %v", err))
	}
	if err := os.WriteFile(filepath.Join(path, identityDocFileName), documentBytes, 0o644); err != nil {
		return ValidationError(fmt.Sprintf("unable to persist identity document: %v", err))
	}
	return nil
}

func ReadIdentity(storageDir string, agentID string) (*IdentityBundle, error) {
	path := identityPath(storageDir, agentID)
	identityBytes, err := os.ReadFile(filepath.Join(path, identityFileName))
	if err != nil {
		return nil, nil
	}
	documentBytes, err := os.ReadFile(filepath.Join(path, identityDocFileName))
	if err != nil {
		return nil, nil
	}
	var identity AgentIdentity
	if err := json.Unmarshal(identityBytes, &identity); err != nil {
		return nil, ValidationError(fmt.Sprintf("invalid stored identity: %v", err))
	}
	document, err := ParseJSONMap(documentBytes)
	if err != nil {
		return nil, err
	}
	return &IdentityBundle{
		Identity:         identity,
		IdentityDocument: document,
	}, nil
}

func IdentityFromProvider(input ProviderIdentityInput) (AgentIdentity, error) {
	signingPublicKey := strings.TrimSpace(input.SigningPublicKey)
	if signingPublicKey == "" {
		derived, err := Ed25519PublicFromPrivate(input.SigningPrivateKey)
		if err != nil {
			return AgentIdentity{}, err
		}
		signingPublicKey = derived
	}
	encryptionPublicKey := strings.TrimSpace(input.EncryptionPublicKey)
	if encryptionPublicKey == "" {
		derived, err := X25519PublicFromPrivate(input.EncryptionPrivateKey)
		if err != nil {
			return AgentIdentity{}, err
		}
		encryptionPublicKey = derived
	}
	signingKID := strings.TrimSpace(input.SigningKID)
	if signingKID == "" {
		signingKID = "sig-" + strings.ReplaceAll(uuid.NewString(), "-", "")[:12]
	}
	encryptionKID := strings.TrimSpace(input.EncryptionKID)
	if encryptionKID == "" {
		encryptionKID = "enc-" + strings.ReplaceAll(uuid.NewString(), "-", "")[:12]
	}
	return AgentIdentity{
		AgentID:              input.AgentID,
		SigningPrivateKey:    input.SigningPrivateKey,
		SigningPublicKey:     signingPublicKey,
		EncryptionPrivateKey: input.EncryptionPrivateKey,
		EncryptionPublicKey:  encryptionPublicKey,
		SigningKID:           signingKID,
		EncryptionKID:        encryptionKID,
	}, nil
}

func copyMap(input map[string]any) map[string]any {
	output := map[string]any{}
	for key, value := range input {
		output[key] = value
	}
	return output
}

func mapOrDefault(input map[string]any) map[string]any {
	if input == nil {
		return map[string]any{}
	}
	return input
}
