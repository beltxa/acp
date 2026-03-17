/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

type InboundResult struct {
	State            DeliveryState  `json:"state"`
	ReasonCode       string         `json:"reason_code,omitempty"`
	Detail           string         `json:"detail,omitempty"`
	DecryptedPayload map[string]any `json:"decrypted_payload,omitempty"`
	ResponseMessage  map[string]any `json:"response_message,omitempty"`
}

type DecryptedMessage struct {
	Message AcpMessage
	Payload map[string]any
}

type CapabilityRequestResult struct {
	Result       SendResult     `json:"result"`
	Capabilities map[string]any `json:"capabilities,omitempty"`
}

type InboundHandler func(payload map[string]any, envelope Envelope) map[string]any

type resolvedRecipient struct {
	Recipient   string
	PublicKey   string
	Channel     string
	Endpoint    string
	AMQPService map[string]any
	MQTTService map[string]any
}

type channelChoice struct {
	Channel     string
	Endpoint    string
	AMQPService map[string]any
	MQTTService map[string]any
	Detail      string
}

type keyProviderInfo map[string]any

type dedupStore struct {
	ttl  time.Duration
	lock sync.Mutex
	seen map[string]time.Time
}

func newDedupStore(ttl time.Duration) *dedupStore {
	return &dedupStore{
		ttl:  ttl,
		seen: map[string]time.Time{},
	}
}

func (store *dedupStore) isDuplicate(messageID string) bool {
	store.lock.Lock()
	defer store.lock.Unlock()
	store.cleanupLocked()
	_, ok := store.seen[messageID]
	return ok
}

func (store *dedupStore) markProcessed(messageID string) {
	store.lock.Lock()
	store.seen[messageID] = time.Now().UTC()
	store.cleanupLocked()
	store.lock.Unlock()
}

func (store *dedupStore) cleanupLocked() {
	cutoff := time.Now().UTC().Add(-store.ttl)
	for messageID, timestamp := range store.seen {
		if timestamp.Before(cutoff) {
			delete(store.seen, messageID)
		}
	}
}

type AcpAgent struct {
	Identity            AgentIdentity
	IdentityDocument    map[string]any
	Discovery           *DiscoveryClient
	Transport           *TransportClient
	AMQPTransport       *AmqpTransportClient
	MQTTTransport       *MqttTransportClient
	Capabilities        AgentCapabilities
	StorageDir          string
	TrustProfile        string
	RelayURL            string
	DefaultDeliveryMode DeliveryMode
	KeyProviderInfo     map[string]any

	dedup *dedupStore

	deliveryStatesLock sync.Mutex
	deliveryStates     map[string]map[string]string
}

func LoadOrCreate(agentID string, optionsInput *AcpAgentOptions) (*AcpAgent, error) {
	if _, err := ParseAgentID(agentID); err != nil {
		return nil, err
	}
	options := mergeAgentOptions(DefaultAgentOptions(), optionsInput)
	if err := os.MkdirAll(options.StorageDir, 0o755); err != nil {
		return nil, ValidationError(fmt.Sprintf("unable to create storage directory: %v", err))
	}
	keyProvider, err := resolveKeyProvider(options)
	if err != nil {
		return nil, err
	}
	keyProviderInfo := keyProvider.Describe()
	providerIdentityKeys, _ := keyProvider.LoadIdentityKeys(agentID)
	providerTLS, _ := keyProvider.LoadTLSMaterial(agentID)
	providerCA, _ := keyProvider.LoadCABundle(agentID)

	effectiveCAFile := firstNonBlankString(options.CAFile, providerTLS.CAFile, providerCA)
	effectiveCertFile := firstNonBlankString(options.CertFile, providerTLS.CertFile)
	effectiveKeyFile := firstNonBlankString(options.KeyFile, providerTLS.KeyFile)
	policy := HTTPSecurityPolicy{
		AllowInsecureHTTP: options.AllowInsecureHTTP,
		AllowInsecureTLS:  options.AllowInsecureTLS,
		MTLSEnabled:       options.MTLSEnabled,
		CAFile:            effectiveCAFile,
		CertFile:          effectiveCertFile,
		KeyFile:           effectiveKeyFile,
	}
	if err := ValidateHTTPClientPolicy(policy, "Agent HTTP security configuration"); err != nil {
		return nil, err
	}
	if options.Endpoint != "" {
		if _, err := ValidateHTTPURL(options.Endpoint, policy.AllowInsecureHTTP, policy.MTLSEnabled, "Agent direct endpoint configuration"); err != nil {
			return nil, err
		}
		if policy.AllowInsecureHTTP {
			WarnIfInsecureHTTPUsed(options.Endpoint, "Agent direct endpoint configuration")
		}
	}
	if _, err := ValidateHTTPURL(options.RelayURL, policy.AllowInsecureHTTP, policy.MTLSEnabled, "Agent relay URL configuration"); err != nil {
		return nil, err
	}
	for _, relayHint := range options.RelayHints {
		if _, err := ValidateHTTPURL(relayHint, policy.AllowInsecureHTTP, policy.MTLSEnabled, "Agent relay hint configuration"); err != nil {
			return nil, err
		}
	}
	for _, directoryHint := range options.EnterpriseDirectoryHints {
		if _, err := ValidateHTTPURL(directoryHint, policy.AllowInsecureHTTP, policy.MTLSEnabled, "Agent enterprise directory hint configuration"); err != nil {
			return nil, err
		}
	}

	localAMQPService, err := buildLocalAMQPService(agentID, options)
	if err != nil {
		return nil, err
	}
	localMQTTService, err := buildLocalMQTTService(agentID, options)
	if err != nil {
		return nil, err
	}

	var identity AgentIdentity
	var identityDocument map[string]any
	var capabilities AgentCapabilities

	bundle, err := ReadIdentity(options.StorageDir, agentID)
	if err != nil {
		return nil, err
	}
	if bundle == nil {
		if providerIdentityKeys != nil {
			identity, err = IdentityFromProvider(ProviderIdentityInput{
				AgentID:              agentID,
				SigningPrivateKey:    providerIdentityKeys.SigningPrivateKey,
				EncryptionPrivateKey: providerIdentityKeys.EncryptionPrivateKey,
				SigningPublicKey:     providerIdentityKeys.SigningPublicKey,
				EncryptionPublicKey:  providerIdentityKeys.EncryptionPublicKey,
				SigningKID:           providerIdentityKeys.SigningKID,
				EncryptionKID:        providerIdentityKeys.EncryptionKID,
			})
			if err != nil {
				return nil, err
			}
		} else {
			identity, err = CreateIdentity(agentID)
			if err != nil {
				return nil, err
			}
		}
		capabilities = NewAgentCapabilities(agentID)
		identityDocument, err = BuildIdentityDocument(BuildIdentityDocumentInput{
			Identity:             identity,
			DirectEndpoint:       options.Endpoint,
			RelayHints:           options.RelayHints,
			TrustProfile:         options.TrustProfile,
			Capabilities:         capabilities.ToMap(),
			ValidDays:            365,
			AMQPService:          localAMQPService,
			MQTTService:          localMQTTService,
			HTTPSecurityProfile:  mapSecurityProfile(options.Endpoint, options.MTLSEnabled),
			RelaySecurityProfile: mapSecurityProfile(options.RelayURL, options.MTLSEnabled),
		})
		if err != nil {
			return nil, err
		}
		applyHTTPSecurityProfile(identityDocument, options.MTLSEnabled)
		if err := resignIdentityDocument(identityDocument, identity); err != nil {
			return nil, err
		}
		if err := WriteIdentity(options.StorageDir, identity, identityDocument); err != nil {
			return nil, err
		}
	} else {
		identity = bundle.Identity
		identityDocument = bundle.IdentityDocument
		if providerIdentityKeys != nil {
			identity, err = IdentityFromProvider(ProviderIdentityInput{
				AgentID:              identity.AgentID,
				SigningPrivateKey:    providerIdentityKeys.SigningPrivateKey,
				EncryptionPrivateKey: providerIdentityKeys.EncryptionPrivateKey,
				SigningPublicKey:     firstNonBlankString(providerIdentityKeys.SigningPublicKey, identity.SigningPublicKey),
				EncryptionPublicKey:  firstNonBlankString(providerIdentityKeys.EncryptionPublicKey, identity.EncryptionPublicKey),
				SigningKID:           firstNonBlankString(providerIdentityKeys.SigningKID, identity.SigningKID),
				EncryptionKID:        firstNonBlankString(providerIdentityKeys.EncryptionKID, identity.EncryptionKID),
			})
			if err != nil {
				return nil, err
			}
		}
		capabilitiesRaw, _ := identityDocument["capabilities"].(map[string]any)
		capabilities = AgentCapabilitiesFromMap(capabilitiesRaw, agentID)
		rewrite := !VerifyIdentityDocument(identityDocument) || options.Endpoint != "" || len(options.RelayHints) > 0 || localAMQPService != nil || localMQTTService != nil
		if rewrite {
			service, _ := identityDocument["service"].(map[string]any)
			existingEndpoint, _ := service["direct_endpoint"].(string)
			relayHints := options.RelayHints
			if len(relayHints) == 0 {
				if rawHints, ok := service["relay_hints"].([]any); ok {
					for _, rawHint := range rawHints {
						if hint, ok := rawHint.(string); ok && strings.TrimSpace(hint) != "" {
							relayHints = append(relayHints, strings.TrimSpace(hint))
						}
					}
				}
			}
			identityDocument, err = BuildIdentityDocument(BuildIdentityDocumentInput{
				Identity:             identity,
				DirectEndpoint:       firstNonBlankString(options.Endpoint, existingEndpoint),
				RelayHints:           relayHints,
				TrustProfile:         options.TrustProfile,
				Capabilities:         capabilities.ToMap(),
				ValidDays:            365,
				AMQPService:          coalesceMap(localAMQPService, asMap(service["amqp"])),
				MQTTService:          coalesceMap(localMQTTService, asMap(service["mqtt"])),
				HTTPSecurityProfile:  mapSecurityProfile(firstNonBlankString(options.Endpoint, existingEndpoint), options.MTLSEnabled),
				RelaySecurityProfile: mapSecurityProfile(options.RelayURL, options.MTLSEnabled),
			})
			if err != nil {
				return nil, err
			}
			applyHTTPSecurityProfile(identityDocument, options.MTLSEnabled)
			if err := resignIdentityDocument(identityDocument, identity); err != nil {
				return nil, err
			}
			if err := WriteIdentity(options.StorageDir, identity, identityDocument); err != nil {
				return nil, err
			}
		}
	}

	effectiveRelayHints := options.RelayHints
	if len(effectiveRelayHints) == 0 {
		service, _ := identityDocument["service"].(map[string]any)
		if rawHints, ok := service["relay_hints"].([]any); ok {
			for _, raw := range rawHints {
				if hint, ok := raw.(string); ok && strings.TrimSpace(hint) != "" {
					effectiveRelayHints = append(effectiveRelayHints, strings.TrimSpace(hint))
				}
			}
		}
	}
	discovery, err := NewDiscoveryClient(
		filepath.Join(options.StorageDir, "discovery-cache.json"),
		options.DiscoveryScheme,
		effectiveRelayHints,
		options.EnterpriseDirectoryHints,
		options.HTTPTimeoutSeconds,
		policy,
	)
	if err != nil {
		return nil, err
	}
	discovery.Seed(identityDocument)
	transport, err := NewTransportClient(options.HTTPTimeoutSeconds, policy)
	if err != nil {
		return nil, err
	}
	var amqpTransport *AmqpTransportClient
	if options.AMQPBrokerURL != "" {
		amqpTransport, err = NewAmqpTransportClient(options.AMQPBrokerURL, options.AMQPExchange, options.AMQPExchangeType, options.HTTPTimeoutSeconds)
		if err != nil {
			return nil, err
		}
	}
	var mqttTransport *MqttTransportClient
	if options.MQTTBrokerURL != "" {
		mqttTransport, err = NewMqttTransportClient(options.MQTTBrokerURL, options.MQTTQoS, options.MQTTTopicPrefix, options.HTTPTimeoutSeconds, 30)
		if err != nil {
			return nil, err
		}
	}
	return &AcpAgent{
		Identity:            identity,
		IdentityDocument:    identityDocument,
		Discovery:           discovery,
		Transport:           transport,
		AMQPTransport:       amqpTransport,
		MQTTTransport:       mqttTransport,
		Capabilities:        capabilities,
		StorageDir:          options.StorageDir,
		TrustProfile:        options.TrustProfile,
		RelayURL:            options.RelayURL,
		DefaultDeliveryMode: options.DefaultDeliveryMode,
		KeyProviderInfo:     keyProviderInfo,
		dedup:               newDedupStore(time.Hour),
		deliveryStates:      map[string]map[string]string{},
	}, nil
}

func mergeAgentOptions(base AcpAgentOptions, override *AcpAgentOptions) AcpAgentOptions {
	if override == nil {
		return base
	}
	merged := base
	if strings.TrimSpace(override.StorageDir) != "" {
		merged.StorageDir = strings.TrimSpace(override.StorageDir)
	}
	if strings.TrimSpace(override.Endpoint) != "" {
		merged.Endpoint = strings.TrimSpace(override.Endpoint)
	}
	if strings.TrimSpace(override.RelayURL) != "" {
		merged.RelayURL = strings.TrimSpace(override.RelayURL)
	}
	if len(override.RelayHints) > 0 {
		merged.RelayHints = append([]string{}, override.RelayHints...)
	}
	if len(override.EnterpriseDirectoryHints) > 0 {
		merged.EnterpriseDirectoryHints = append([]string{}, override.EnterpriseDirectoryHints...)
	}
	if strings.TrimSpace(override.DiscoveryScheme) != "" {
		merged.DiscoveryScheme = strings.TrimSpace(override.DiscoveryScheme)
	}
	if strings.TrimSpace(override.TrustProfile) != "" {
		merged.TrustProfile = strings.TrimSpace(override.TrustProfile)
	}
	if override.DefaultDeliveryMode != "" {
		merged.DefaultDeliveryMode = override.DefaultDeliveryMode
	}
	if override.HTTPTimeoutSeconds > 0 {
		merged.HTTPTimeoutSeconds = override.HTTPTimeoutSeconds
	}
	merged.AllowInsecureHTTP = override.AllowInsecureHTTP
	merged.AllowInsecureTLS = override.AllowInsecureTLS
	merged.MTLSEnabled = override.MTLSEnabled
	if override.CAFile != "" {
		merged.CAFile = override.CAFile
	}
	if override.CertFile != "" {
		merged.CertFile = override.CertFile
	}
	if override.KeyFile != "" {
		merged.KeyFile = override.KeyFile
	}
	if override.KeyProvider != "" {
		merged.KeyProvider = override.KeyProvider
	}
	if override.VaultURL != "" {
		merged.VaultURL = override.VaultURL
	}
	if override.VaultPath != "" {
		merged.VaultPath = override.VaultPath
	}
	if override.VaultTokenEnv != "" {
		merged.VaultTokenEnv = override.VaultTokenEnv
	}
	if override.VaultToken != "" {
		merged.VaultToken = override.VaultToken
	}
	if override.AMQPBrokerURL != "" {
		merged.AMQPBrokerURL = override.AMQPBrokerURL
	}
	if override.AMQPExchange != "" {
		merged.AMQPExchange = override.AMQPExchange
	}
	if override.AMQPExchangeType != "" {
		merged.AMQPExchangeType = override.AMQPExchangeType
	}
	if override.MQTTBrokerURL != "" {
		merged.MQTTBrokerURL = override.MQTTBrokerURL
	}
	if override.MQTTQoS != 0 {
		merged.MQTTQoS = override.MQTTQoS
	}
	if override.MQTTTopicPrefix != "" {
		merged.MQTTTopicPrefix = override.MQTTTopicPrefix
	}
	return merged
}

func resolveKeyProvider(options AcpAgentOptions) (KeyProvider, error) {
	if options.KeyProvider == "vault" {
		if strings.TrimSpace(options.VaultURL) == "" || strings.TrimSpace(options.VaultPath) == "" {
			return nil, KeyProviderError("vault_url and vault_path are required when key_provider=vault")
		}
		return NewVaultKeyProvider(
			options.VaultURL,
			options.VaultPath,
			options.VaultTokenEnv,
			options.VaultToken,
			options.HTTPTimeoutSeconds,
			options.CAFile,
			options.AllowInsecureTLS,
			options.AllowInsecureHTTP,
		)
	}
	return NewLocalKeyProvider(options.StorageDir, options.CertFile, options.KeyFile, options.CAFile), nil
}

func mapSecurityProfile(endpoint string, mtlsEnabled bool) string {
	if mtlsEnabled {
		return "mtls"
	}
	if strings.HasPrefix(strings.ToLower(strings.TrimSpace(endpoint)), "https://") {
		return "https"
	}
	if strings.HasPrefix(strings.ToLower(strings.TrimSpace(endpoint)), "http://") {
		return "http"
	}
	return ""
}

func buildLocalAMQPService(agentID string, options AcpAgentOptions) (map[string]any, error) {
	if strings.TrimSpace(options.AMQPBrokerURL) == "" {
		return nil, nil
	}
	return BuildAMQPServiceHint(agentID, options.AMQPBrokerURL, options.AMQPExchange)
}

func buildLocalMQTTService(agentID string, options AcpAgentOptions) (map[string]any, error) {
	if strings.TrimSpace(options.MQTTBrokerURL) == "" {
		return nil, nil
	}
	return BuildMQTTServiceHint(agentID, options.MQTTBrokerURL, "", options.MQTTQoS, options.MQTTTopicPrefix)
}

func asMap(value any) map[string]any {
	parsed, _ := value.(map[string]any)
	return parsed
}

func coalesceMap(primary map[string]any, fallback map[string]any) map[string]any {
	if primary != nil {
		return primary
	}
	return fallback
}

func applyHTTPSecurityProfile(identityDocument map[string]any, mtlsEnabled bool) {
	service, _ := identityDocument["service"].(map[string]any)
	if service == nil {
		service = map[string]any{}
	}
	if endpoint, ok := service["direct_endpoint"].(string); ok && strings.TrimSpace(endpoint) != "" {
		profile := mapSecurityProfile(endpoint, mtlsEnabled)
		if profile != "" {
			service["http"] = map[string]any{
				"endpoint":         strings.TrimSpace(endpoint),
				"security_profile": profile,
			}
		}
	}
	if rawHints, ok := service["relay_hints"].([]any); ok && len(rawHints) > 0 {
		firstHint, _ := rawHints[0].(string)
		firstHint = strings.TrimSpace(firstHint)
		if firstHint != "" {
			profile := mapSecurityProfile(firstHint, mtlsEnabled)
			if profile != "" {
				service["relay"] = map[string]any{
					"endpoint":         firstHint,
					"security_profile": profile,
				}
			}
		}
	}
	identityDocument["service"] = service
}

func resignIdentityDocument(identityDocument map[string]any, identity AgentIdentity) error {
	unsigned := copyMap(identityDocument)
	delete(unsigned, "signature")
	signatureInput, err := CanonicalJSONBytes(unsigned)
	if err != nil {
		return err
	}
	signatureValue, err := SignBytes(signatureInput, identity.SigningPrivateKey)
	if err != nil {
		return err
	}
	identityDocument["signature"] = map[string]any{
		"algorithm": "Ed25519",
		"signed_by": identity.SigningKID,
		"value":     signatureValue,
	}
	return nil
}

func (agent *AcpAgent) AgentID() string {
	return agent.Identity.AgentID
}

func (agent *AcpAgent) GetDeliveryStates() map[string]map[string]string {
	agent.deliveryStatesLock.Lock()
	defer agent.deliveryStatesLock.Unlock()
	output := map[string]map[string]string{}
	for operationID, states := range agent.deliveryStates {
		output[operationID] = map[string]string{}
		for recipient, state := range states {
			output[operationID][recipient] = state
		}
	}
	return output
}

func (agent *AcpAgent) BuildWellKnownDocument(baseURL string, identityDocumentURL string) (map[string]any, error) {
	resolvedBaseURL := strings.TrimSpace(baseURL)
	if resolvedBaseURL == "" {
		service, _ := agent.IdentityDocument["service"].(map[string]any)
		endpoint, _ := service["direct_endpoint"].(string)
		endpoint = strings.TrimSpace(endpoint)
		if endpoint == "" {
			return nil, ValidationError("Unable to build /.well-known/acp metadata without base_url or direct_endpoint")
		}
		resolvedBaseURL = endpoint
		if strings.Contains(endpoint, "/") {
			parts := strings.SplitN(strings.TrimPrefix(endpoint, "https://"), "/", 2)
			if len(parts) > 0 && strings.HasPrefix(endpoint, "https://") {
				resolvedBaseURL = "https://" + parts[0]
			}
			if strings.HasPrefix(endpoint, "http://") {
				parts = strings.SplitN(strings.TrimPrefix(endpoint, "http://"), "/", 2)
				resolvedBaseURL = "http://" + parts[0]
			}
		}
	}
	return BuildWellKnownDocument(BuildWellKnownInput{
		IdentityDocument:    agent.IdentityDocument,
		BaseURL:             resolvedBaseURL,
		IdentityDocumentURL: identityDocumentURL,
		Version:             ACPVersion,
	})
}

func (agent *AcpAgent) RegisterIdentityDocument(identityDocument map[string]any) error {
	return agent.Discovery.RegisterIdentityDocument(identityDocument)
}

func (agent *AcpAgent) ResolveWellKnown(baseURL string, expectedAgentID string) (map[string]any, error) {
	return agent.Discovery.ResolveWellKnown(baseURL, expectedAgentID)
}

func parseReasonForCapabilityMismatch(reason string) FailReason {
	normalized := strings.ToLower(reason)
	switch {
	case strings.Contains(normalized, "protocol"):
		return FailUnsupportedVersion
	case strings.Contains(normalized, "crypto"):
		return FailUnsupportedCryptoSuite
	case strings.Contains(normalized, "profile"):
		return FailUnsupportedProfile
	default:
		return FailPolicyRejected
	}
}

func failedOutcome(recipient string, reasonCode string, detail string) DeliveryOutcome {
	return DeliveryOutcome{
		Recipient:  recipient,
		State:      StateFailed,
		ReasonCode: &reasonCode,
		Detail:     &detail,
	}
}

func toPublicKeyMap(targets []resolvedRecipient) map[string]string {
	output := map[string]string{}
	for _, target := range targets {
		output[target.Recipient] = target.PublicKey
	}
	return output
}

func (agent *AcpAgent) resolveRecipients(recipients []string, mode DeliveryMode) ([]resolvedRecipient, []DeliveryOutcome) {
	deliverable := []resolvedRecipient{}
	preflight := []DeliveryOutcome{}
	for _, recipient := range recipients {
		identityDocument, err := agent.Discovery.Resolve(recipient)
		if err != nil {
			preflight = append(preflight, failedOutcome(recipient, string(FailPolicyRejected), err.Error()))
			continue
		}
		remoteCapabilities := AgentCapabilitiesFromMap(asMap(identityDocument["capabilities"]), recipient)
		match := agent.Capabilities.ChooseCompatible(remoteCapabilities)
		if !match.Compatible {
			reason := parseReasonForCapabilityMismatch(match.Reason)
			preflight = append(preflight, failedOutcome(recipient, string(reason), firstNonBlankString(match.Reason, "No compatible capabilities")))
			continue
		}
		choice := agent.chooseDeliveryChannel(remoteCapabilities, identityDocument, mode)
		if choice.Channel == "" {
			preflight = append(preflight, failedOutcome(recipient, string(FailPolicyRejected), firstNonBlankString(choice.Detail, "Delivery channel unavailable")))
			continue
		}
		keys := asMap(identityDocument["keys"])
		encryption := asMap(keys["encryption"])
		publicKey, _ := encryption["public_key"].(string)
		publicKey = strings.TrimSpace(publicKey)
		if publicKey == "" {
			preflight = append(preflight, failedOutcome(recipient, string(FailPolicyRejected), "Recipient identity document missing encryption public key"))
			continue
		}
		deliverable = append(deliverable, resolvedRecipient{
			Recipient:   recipient,
			PublicKey:   publicKey,
			Channel:     choice.Channel,
			Endpoint:    choice.Endpoint,
			AMQPService: choice.AMQPService,
			MQTTService: choice.MQTTService,
		})
	}
	return deliverable, preflight
}

func (agent *AcpAgent) chooseDeliveryChannel(
	remoteCapabilities AgentCapabilities,
	identityDocument map[string]any,
	mode DeliveryMode,
) channelChoice {
	shared := []string{}
	remoteSet := map[string]struct{}{}
	for _, transport := range remoteCapabilities.Transports {
		remoteSet[strings.ToLower(transport)] = struct{}{}
	}
	for _, transport := range agent.Capabilities.Transports {
		normalized := strings.ToLower(transport)
		if _, ok := remoteSet[normalized]; ok {
			shared = append(shared, normalized)
		}
	}
	service := asMap(identityDocument["service"])
	directEndpoint, _ := service["direct_endpoint"].(string)
	directEndpoint = strings.TrimSpace(directEndpoint)
	amqpService := asMap(service["amqp"])
	mqttService := asMap(service["mqtt"])
	directAvailable := directEndpoint != "" && containsAny(shared, "https", "http", "direct")
	relayAvailable := strings.TrimSpace(agent.RelayURL) != "" && containsAny(shared, "relay")
	amqpAvailable := amqpService != nil && containsAny(shared, "amqp")
	mqttAvailable := mqttService != nil && containsAny(shared, "mqtt")

	switch mode {
	case DeliveryDirect:
		if directAvailable {
			return channelChoice{Channel: "direct", Endpoint: directEndpoint}
		}
		return channelChoice{Detail: "Recipient direct endpoint is unavailable or incompatible"}
	case DeliveryRelay:
		if relayAvailable {
			return channelChoice{Channel: "relay"}
		}
		return channelChoice{Detail: "Relay delivery is unavailable or incompatible"}
	case DeliveryAMQP:
		if amqpAvailable {
			return channelChoice{Channel: "amqp", AMQPService: amqpService}
		}
		return channelChoice{Detail: "AMQP delivery is unavailable or incompatible"}
	case DeliveryMQTT:
		if mqttAvailable {
			return channelChoice{Channel: "mqtt", MQTTService: mqttService}
		}
		return channelChoice{Detail: "MQTT delivery is unavailable or incompatible"}
	default:
		if directAvailable {
			return channelChoice{Channel: "direct", Endpoint: directEndpoint}
		}
		if relayAvailable {
			return channelChoice{Channel: "relay"}
		}
		if amqpAvailable {
			return channelChoice{Channel: "amqp", AMQPService: amqpService}
		}
		if mqttAvailable {
			return channelChoice{Channel: "mqtt", MQTTService: mqttService}
		}
		return channelChoice{
			Detail: "Recipient identity document is missing direct_endpoint/amqp/mqtt and no relay fallback is compatible",
		}
	}
}

func containsAny(items []string, candidates ...string) bool {
	set := map[string]struct{}{}
	for _, item := range items {
		set[item] = struct{}{}
	}
	for _, candidate := range candidates {
		if _, ok := set[candidate]; ok {
			return true
		}
	}
	return false
}

func (agent *AcpAgent) buildMessage(
	recipients []string,
	payload map[string]any,
	recipientPublicKeys map[string]string,
	messageClass MessageClass,
	contextID string,
	operationID string,
	expiresInSeconds int,
	correlationID string,
	inReplyTo string,
) (AcpMessage, error) {
	envelope, err := BuildEnvelope(EnvelopeInput{
		Sender:           agent.AgentID(),
		Recipients:       recipients,
		MessageClass:     messageClass,
		ContextID:        contextID,
		OperationID:      operationID,
		ExpiresInSeconds: expiresInSeconds,
		CorrelationID:    correlationID,
		InReplyTo:        inReplyTo,
		CryptoSuite:      DefaultCryptoSuite,
	})
	if err != nil {
		return AcpMessage{}, err
	}
	protectedPayload, err := EncryptForRecipients(payload, envelope, recipientPublicKeys)
	if err != nil {
		return AcpMessage{}, err
	}
	protectedPayload, err = SignProtectedPayload(envelope, protectedPayload, agent.Identity.SigningPrivateKey, agent.Identity.SigningKID)
	if err != nil {
		return AcpMessage{}, err
	}
	return AcpMessage{
		Envelope:               envelope,
		Protected:              protectedPayload,
		SenderIdentityDocument: agent.IdentityDocument,
	}, nil
}

func deliveryStateFromResponse(statusCode int, responseClass *MessageClass, reasonCode string) DeliveryState {
	if statusCode >= 200 && statusCode < 300 {
		if responseClass != nil && *responseClass == MessageFail {
			if reasonCode == string(FailExpiredMessage) {
				return StateExpired
			}
			if reasonCode == string(FailPolicyRejected) {
				return StateDeclined
			}
			return StateFailed
		}
		if responseClass != nil && (*responseClass == MessageAck || *responseClass == MessageCapabilities) {
			return StateAcknowledged
		}
		return StateDelivered
	}
	if statusCode == 410 {
		return StateExpired
	}
	if statusCode == 401 || statusCode == 403 || statusCode == 409 || statusCode == 422 {
		return StateDeclined
	}
	return StateFailed
}

func outcomeFromHTTPResponse(recipient string, response *TransportResponse) DeliveryOutcome {
	var responseMessage map[string]any
	var responseClass *MessageClass
	reasonCode := ""
	detail := ""
	if response.Body != nil {
		if raw, ok := response.Body["response_message"].(map[string]any); ok {
			responseMessage = raw
			if envelopeRaw, ok := raw["envelope"].(map[string]any); ok {
				if messageClassRaw, ok := envelopeRaw["message_class"].(string); ok {
					responseClass = ParseMessageClass(messageClassRaw)
				}
			}
		}
		if rawReason, ok := response.Body["reason_code"].(string); ok {
			reasonCode = rawReason
		}
		if rawDetail, ok := response.Body["detail"].(string); ok {
			detail = rawDetail
		}
	}
	if detail == "" && response.StatusCode >= 400 {
		detail = fmt.Sprintf("Recipient HTTP %d", response.StatusCode)
	}
	outcome := DeliveryOutcome{
		Recipient:       recipient,
		State:           deliveryStateFromResponse(response.StatusCode, responseClass, reasonCode),
		StatusCode:      &response.StatusCode,
		ResponseClass:   responseClass,
		ResponseMessage: responseMessage,
	}
	if reasonCode != "" {
		outcome.ReasonCode = &reasonCode
	}
	if detail != "" {
		outcome.Detail = &detail
	}
	return outcome
}

func (agent *AcpAgent) deliverDirect(message AcpMessage, targets []resolvedRecipient) []DeliveryOutcome {
	messageMap, _ := MessageToMap(message)
	outcomes := []DeliveryOutcome{}
	for _, target := range targets {
		if target.Endpoint == "" {
			outcomes = append(outcomes, failedOutcome(target.Recipient, string(FailPolicyRejected), "Recipient direct endpoint missing"))
			continue
		}
		response, err := agent.Transport.PostJSON(target.Endpoint, messageMap)
		if err != nil {
			outcomes = append(outcomes, failedOutcome(target.Recipient, string(FailPolicyRejected), "Direct transport failure: "+err.Error()))
			continue
		}
		outcomes = append(outcomes, outcomeFromHTTPResponse(target.Recipient, response))
	}
	return outcomes
}

func (agent *AcpAgent) deliverRelay(message AcpMessage, targets []resolvedRecipient) []DeliveryOutcome {
	outcomes := []DeliveryOutcome{}
	relayResponse, err := agent.Transport.SendToRelay(agent.RelayURL, message)
	if err != nil {
		for _, target := range targets {
			outcomes = append(outcomes, failedOutcome(target.Recipient, string(FailPolicyRejected), "Relay transport failure: "+err.Error()))
		}
		return outcomes
	}
	rawOutcomes, ok := relayResponse["outcomes"].([]any)
	if !ok || len(rawOutcomes) == 0 {
		for _, target := range targets {
			outcomes = append(outcomes, DeliveryOutcome{
				Recipient: target.Recipient,
				State:     StateDelivered,
			})
		}
		return outcomes
	}
	for _, rawOutcome := range rawOutcomes {
		item, _ := rawOutcome.(map[string]any)
		recipient, _ := item["recipient"].(string)
		stateRaw, _ := item["state"].(string)
		statusCodePtr := (*int)(nil)
		if rawStatus, ok := item["status_code"].(float64); ok {
			statusCode := int(rawStatus)
			statusCodePtr = &statusCode
		}
		var responseClass *MessageClass
		if rawResponseClass, ok := item["response_class"].(string); ok {
			responseClass = ParseMessageClass(rawResponseClass)
		}
		reasonCode, _ := item["reason_code"].(string)
		detail, _ := item["detail"].(string)
		responseMessage, _ := item["response_message"].(map[string]any)
		state := DeliveryState(stateRaw)
		if state == "" {
			state = StateDelivered
		}
		outcome := DeliveryOutcome{
			Recipient:       recipient,
			State:           state,
			StatusCode:      statusCodePtr,
			ResponseClass:   responseClass,
			ResponseMessage: responseMessage,
		}
		if reasonCode != "" {
			outcome.ReasonCode = &reasonCode
		}
		if detail != "" {
			outcome.Detail = &detail
		}
		outcomes = append(outcomes, outcome)
	}
	return outcomes
}

func (agent *AcpAgent) deliverAMQP(message AcpMessage, target resolvedRecipient) DeliveryOutcome {
	outcome := DeliveryOutcome{
		Recipient: target.Recipient,
		State:     StatePending,
	}
	transportClient := agent.AMQPTransport
	if transportClient == nil {
		brokerURL, _ := target.AMQPService["broker_url"].(string)
		if strings.TrimSpace(brokerURL) == "" {
			detail := "AMQP delivery selected but sender is not configured with an AMQP broker"
			reason := string(FailPolicyRejected)
			outcome.State = StateFailed
			outcome.ReasonCode = &reason
			outcome.Detail = &detail
			return outcome
		}
		client, err := NewAmqpTransportClient(brokerURL, asString(target.AMQPService["exchange"]), "", 10)
		if err != nil {
			detail := err.Error()
			reason := string(FailPolicyRejected)
			outcome.State = StateFailed
			outcome.ReasonCode = &reason
			outcome.Detail = &detail
			return outcome
		}
		transportClient = client
	}
	messageMap, _ := MessageToMap(message)
	if err := transportClient.Publish(messageMap, target.Recipient, target.AMQPService); err != nil {
		reason := string(FailPolicyRejected)
		detail := "AMQP transport failure: " + err.Error()
		outcome.State = StateFailed
		outcome.ReasonCode = &reason
		outcome.Detail = &detail
		return outcome
	}
	outcome.State = StateDelivered
	return outcome
}

func (agent *AcpAgent) deliverMQTT(message AcpMessage, target resolvedRecipient) DeliveryOutcome {
	outcome := DeliveryOutcome{
		Recipient: target.Recipient,
		State:     StatePending,
	}
	transportClient := agent.MQTTTransport
	if transportClient == nil {
		brokerURL, _ := target.MQTTService["broker_url"].(string)
		if strings.TrimSpace(brokerURL) == "" {
			reason := string(FailPolicyRejected)
			detail := "MQTT delivery selected but sender is not configured with an MQTT broker"
			outcome.State = StateFailed
			outcome.ReasonCode = &reason
			outcome.Detail = &detail
			return outcome
		}
		client, err := NewMqttTransportClient(brokerURL, 1, DefaultMQTTTopicPrefix, 10, 30)
		if err != nil {
			reason := string(FailPolicyRejected)
			detail := err.Error()
			outcome.State = StateFailed
			outcome.ReasonCode = &reason
			outcome.Detail = &detail
			return outcome
		}
		transportClient = client
	}
	messageMap, _ := MessageToMap(message)
	if err := transportClient.Publish(messageMap, target.Recipient, target.MQTTService); err != nil {
		reason := string(FailPolicyRejected)
		detail := "MQTT transport failure: " + err.Error()
		outcome.State = StateFailed
		outcome.ReasonCode = &reason
		outcome.Detail = &detail
		return outcome
	}
	outcome.State = StateDelivered
	return outcome
}

func (agent *AcpAgent) syncDeliveryStates(operationID string, outcomes []DeliveryOutcome) {
	states := map[string]string{}
	for _, outcome := range outcomes {
		states[outcome.Recipient] = string(outcome.State)
	}
	agent.deliveryStatesLock.Lock()
	agent.deliveryStates[operationID] = states
	agent.deliveryStatesLock.Unlock()
}

func (agent *AcpAgent) Send(
	recipients []string,
	payload map[string]any,
	context string,
	messageClass MessageClass,
	expiresInSeconds int,
	correlationID string,
	inReplyTo string,
	deliveryMode DeliveryMode,
) (SendResult, error) {
	if len(recipients) == 0 {
		return SendResult{}, ValidationError("send() requires at least one recipient")
	}
	mode := deliveryMode
	if mode == "" {
		mode = agent.DefaultDeliveryMode
	}
	operationID := uuid.NewString()
	contextID := strings.TrimSpace(context)
	if contextID == "" {
		contextID = "ctx:" + uuid.NewString()
	}
	deliverable, preflight := agent.resolveRecipients(recipients, mode)
	outcomes := append([]DeliveryOutcome{}, preflight...)
	messageIDs := []string{}

	directTargets := []resolvedRecipient{}
	relayTargets := []resolvedRecipient{}
	amqpTargets := []resolvedRecipient{}
	mqttTargets := []resolvedRecipient{}
	for _, target := range deliverable {
		switch target.Channel {
		case "direct":
			directTargets = append(directTargets, target)
		case "relay":
			relayTargets = append(relayTargets, target)
		case "amqp":
			amqpTargets = append(amqpTargets, target)
		case "mqtt":
			mqttTargets = append(mqttTargets, target)
		}
	}
	if len(directTargets) > 0 {
		message, err := agent.buildMessage(recipientIDs(directTargets), payload, toPublicKeyMap(directTargets), messageClass, contextID, operationID, expiresInSeconds, correlationID, inReplyTo)
		if err != nil {
			return SendResult{}, err
		}
		messageIDs = append(messageIDs, message.Envelope.MessageID)
		outcomes = append(outcomes, agent.deliverDirect(message, directTargets)...)
	}
	if len(relayTargets) > 0 {
		message, err := agent.buildMessage(recipientIDs(relayTargets), payload, toPublicKeyMap(relayTargets), messageClass, contextID, operationID, expiresInSeconds, correlationID, inReplyTo)
		if err != nil {
			return SendResult{}, err
		}
		messageIDs = append(messageIDs, message.Envelope.MessageID)
		outcomes = append(outcomes, agent.deliverRelay(message, relayTargets)...)
	}
	for _, target := range amqpTargets {
		message, err := agent.buildMessage([]string{target.Recipient}, payload, map[string]string{target.Recipient: target.PublicKey}, messageClass, contextID, operationID, expiresInSeconds, correlationID, inReplyTo)
		if err != nil {
			return SendResult{}, err
		}
		messageIDs = append(messageIDs, message.Envelope.MessageID)
		outcomes = append(outcomes, agent.deliverAMQP(message, target))
	}
	for _, target := range mqttTargets {
		message, err := agent.buildMessage([]string{target.Recipient}, payload, map[string]string{target.Recipient: target.PublicKey}, messageClass, contextID, operationID, expiresInSeconds, correlationID, inReplyTo)
		if err != nil {
			return SendResult{}, err
		}
		messageIDs = append(messageIDs, message.Envelope.MessageID)
		outcomes = append(outcomes, agent.deliverMQTT(message, target))
	}
	if len(messageIDs) == 0 {
		messageIDs = append(messageIDs, uuid.NewString())
	}
	result := SendResult{
		OperationID: operationID,
		MessageID:   messageIDs[0],
		MessageIDs:  messageIDs,
		Outcomes:    outcomes,
	}
	agent.syncDeliveryStates(operationID, outcomes)
	return result, nil
}

func recipientIDs(targets []resolvedRecipient) []string {
	out := make([]string, 0, len(targets))
	for _, target := range targets {
		out = append(out, target.Recipient)
	}
	return out
}

func (agent *AcpAgent) SendBasic(recipients []string, payload map[string]any, context string) (SendResult, error) {
	return agent.Send(recipients, payload, context, MessageSend, 300, "", "", agent.DefaultDeliveryMode)
}

func (agent *AcpAgent) resolveSenderIdentityDocument(rawMessage map[string]any, senderID string) (map[string]any, error) {
	if embedded, ok := rawMessage["sender_identity_document"].(map[string]any); ok {
		embeddedAgentID, _ := embedded["agent_id"].(string)
		if embeddedAgentID == senderID && VerifyIdentityDocument(embedded) {
			return embedded, nil
		}
	}
	return agent.Discovery.Resolve(senderID)
}

func (agent *AcpAgent) validateEnvelopeForInbound(envelope Envelope) error {
	if envelope.ACPVersion != ACPVersion {
		return ProcessingError(FailUnsupportedVersion, fmt.Sprintf("Unsupported ACP version: %s", envelope.ACPVersion))
	}
	if envelope.CryptoSuite != DefaultCryptoSuite {
		return ProcessingError(FailUnsupportedCryptoSuite, fmt.Sprintf("Unsupported crypto suite: %s", envelope.CryptoSuite))
	}
	if IsExpired(envelope) {
		return ProcessingError(FailExpiredMessage, "Message is expired")
	}
	return nil
}

func (agent *AcpAgent) createResponseMessage(
	senderIdentityDocument map[string]any,
	requestEnvelope Envelope,
	responseClass MessageClass,
	responsePayload map[string]any,
) (AcpMessage, error) {
	senderID := requestEnvelope.Sender
	keys := asMap(senderIdentityDocument["keys"])
	encryption := asMap(keys["encryption"])
	senderPublicKey, _ := encryption["public_key"].(string)
	senderPublicKey = strings.TrimSpace(senderPublicKey)
	if senderPublicKey == "" {
		return AcpMessage{}, ProcessingError(FailPolicyRejected, "Sender identity document missing encryption key")
	}
	return agent.buildMessage(
		[]string{senderID},
		responsePayload,
		map[string]string{senderID: senderPublicKey},
		responseClass,
		requestEnvelope.ContextID,
		requestEnvelope.OperationID,
		300,
		firstNonBlankString(derefString(requestEnvelope.CorrelationID), requestEnvelope.OperationID),
		requestEnvelope.MessageID,
	)
}

func derefString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func (agent *AcpAgent) DecryptMessageForSelf(rawMessage map[string]any) (DecryptedMessage, error) {
	message, err := ParseAcpMessage(rawMessage)
	if err != nil {
		return DecryptedMessage{}, err
	}
	if err := agent.validateEnvelopeForInbound(message.Envelope); err != nil {
		return DecryptedMessage{}, err
	}
	if !slicesContains(message.Envelope.Recipients, agent.AgentID()) {
		return DecryptedMessage{}, ProcessingError(FailPolicyRejected, "Message is not addressed to this agent")
	}
	senderDoc, err := agent.resolveSenderIdentityDocument(rawMessage, message.Envelope.Sender)
	if err != nil {
		return DecryptedMessage{}, err
	}
	signingKey := strings.TrimSpace(asString(asMap(asMap(senderDoc["keys"])["signing"])["public_key"]))
	if signingKey == "" {
		return DecryptedMessage{}, ProcessingError(FailInvalidSignature, "Sender signing public key missing")
	}
	if !VerifyProtectedPayloadSignature(message.Envelope, message.Protected, signingKey) {
		return DecryptedMessage{}, ProcessingError(FailInvalidSignature, "Message signature verification failed")
	}
	payload, err := DecryptForRecipient(message.Envelope, message.Protected, agent.AgentID(), agent.Identity.EncryptionPrivateKey)
	if err != nil {
		return DecryptedMessage{}, err
	}
	return DecryptedMessage{Message: message, Payload: payload}, nil
}

func slicesContains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func (agent *AcpAgent) Receive(rawMessage map[string]any, handler InboundHandler) InboundResult {
	result := InboundResult{
		State: StateFailed,
	}
	requestMessage, err := ParseAcpMessage(rawMessage)
	if err != nil {
		result.ReasonCode = string(FailPolicyRejected)
		result.Detail = "Invalid ACP message structure: " + err.Error()
		return result
	}
	var senderDoc map[string]any
	if err := agent.validateEnvelopeForInbound(requestMessage.Envelope); err != nil {
		result.ReasonCode = failReasonFromError(err)
		result.Detail = err.Error()
		return result
	}
	if !slicesContains(requestMessage.Envelope.Recipients, agent.AgentID()) {
		result.ReasonCode = string(FailPolicyRejected)
		result.Detail = fmt.Sprintf("Recipient %s not in message recipients", agent.AgentID())
		return result
	}
	senderDoc, err = agent.resolveSenderIdentityDocument(rawMessage, requestMessage.Envelope.Sender)
	if err != nil {
		result.ReasonCode = string(FailPolicyRejected)
		result.Detail = err.Error()
		return result
	}
	signingKey := strings.TrimSpace(asString(asMap(asMap(senderDoc["keys"])["signing"])["public_key"]))
	if signingKey == "" {
		result.ReasonCode = string(FailInvalidSignature)
		result.Detail = "Sender signing key missing from identity document"
		return result
	}
	if !VerifyProtectedPayloadSignature(requestMessage.Envelope, requestMessage.Protected, signingKey) {
		result.ReasonCode = string(FailInvalidSignature)
		result.Detail = "Signature verification failed"
		return result
	}
	if agent.dedup.isDuplicate(requestMessage.Envelope.MessageID) {
		result.State = StateAcknowledged
		result.Detail = "Duplicate message acknowledged"
		if requestMessage.Envelope.MessageClass != MessageAck && requestMessage.Envelope.MessageClass != MessageFail {
			responseMessage, responseErr := agent.createResponseMessage(
				senderDoc,
				requestMessage.Envelope,
				MessageAck,
				BuildAckPayload(requestMessage.Envelope.MessageID, "duplicate"),
			)
			if responseErr == nil {
				result.ResponseMessage, _ = MessageToMap(responseMessage)
			}
		}
		return result
	}
	decrypted, err := DecryptForRecipient(requestMessage.Envelope, requestMessage.Protected, agent.AgentID(), agent.Identity.EncryptionPrivateKey)
	if err != nil {
		result.ReasonCode = string(FailPolicyRejected)
		result.Detail = err.Error()
	} else {
		result.DecryptedPayload = decrypted
		var responseMessage AcpMessage
		var hasResponse bool
		if requestMessage.Envelope.MessageClass == MessageCapabilities {
			responseMessage, err = agent.createResponseMessage(
				senderDoc,
				requestMessage.Envelope,
				MessageCapabilities,
				agent.Capabilities.ToMap(),
			)
			hasResponse = err == nil
		} else if requestMessage.Envelope.MessageClass != MessageAck && requestMessage.Envelope.MessageClass != MessageFail {
			ackPayload := BuildAckPayload(requestMessage.Envelope.MessageID, "accepted")
			if handler != nil {
				handlerPayload := handler(decrypted, requestMessage.Envelope)
				if len(handlerPayload) > 0 {
					ackPayload["handler"] = handlerPayload
				}
			}
			responseMessage, err = agent.createResponseMessage(senderDoc, requestMessage.Envelope, MessageAck, ackPayload)
			hasResponse = err == nil
		}
		agent.dedup.markProcessed(requestMessage.Envelope.MessageID)
		result.State = StateAcknowledged
		if hasResponse {
			result.ResponseMessage, _ = MessageToMap(responseMessage)
		}
		return result
	}
	terminal := requestMessage.Envelope.MessageClass == MessageAck || requestMessage.Envelope.MessageClass == MessageFail
	if !terminal {
		failPayload := BuildFailPayload(firstNonBlankString(result.ReasonCode, string(FailPolicyRejected)), firstNonBlankString(result.Detail, "processing error"), false)
		if responseMessage, responseErr := agent.createResponseMessage(senderDoc, requestMessage.Envelope, MessageFail, failPayload); responseErr == nil {
			result.ResponseMessage, _ = MessageToMap(responseMessage)
		}
	}
	return result
}

func failReasonFromError(err error) string {
	acpErr, ok := err.(*AcpError)
	if !ok || acpErr.Reason == nil {
		return string(FailPolicyRejected)
	}
	return string(*acpErr.Reason)
}

func (agent *AcpAgent) RequestCapabilities(recipient string) (CapabilityRequestResult, error) {
	result, err := agent.Send([]string{recipient}, map[string]any{}, "capabilities:"+uuid.NewString(), MessageCapabilities, 300, "", "", agent.DefaultDeliveryMode)
	if err != nil {
		return CapabilityRequestResult{}, err
	}
	var capabilities map[string]any
	for _, outcome := range result.Outcomes {
		if outcome.ResponseMessage == nil {
			continue
		}
		decrypted, err := agent.DecryptMessageForSelf(outcome.ResponseMessage)
		if err != nil {
			continue
		}
		if decrypted.Message.Envelope.MessageClass == MessageCapabilities {
			capabilities = decrypted.Payload
			break
		}
	}
	return CapabilityRequestResult{
		Result:       result,
		Capabilities: capabilities,
	}, nil
}

func (agent *AcpAgent) MarshalJSON() ([]byte, error) {
	type alias struct {
		Identity            AgentIdentity  `json:"identity"`
		IdentityDocument    map[string]any `json:"identity_document"`
		Capabilities        map[string]any `json:"capabilities"`
		StorageDir          string         `json:"storage_dir"`
		TrustProfile        string         `json:"trust_profile"`
		RelayURL            string         `json:"relay_url"`
		DefaultDeliveryMode DeliveryMode   `json:"default_delivery_mode"`
		KeyProviderInfo     map[string]any `json:"key_provider_info"`
	}
	return json.Marshal(alias{
		Identity:            agent.Identity,
		IdentityDocument:    agent.IdentityDocument,
		Capabilities:        agent.Capabilities.ToMap(),
		StorageDir:          agent.StorageDir,
		TrustProfile:        agent.TrustProfile,
		RelayURL:            agent.RelayURL,
		DefaultDeliveryMode: agent.DefaultDeliveryMode,
		KeyProviderInfo:     agent.KeyProviderInfo,
	})
}
