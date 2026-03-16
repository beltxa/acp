package acp

import (
	"fmt"
	"net/url"
	"slices"
	"strings"
)

var supportedWellKnownSecurityProfiles = []string{"http", "https", "mtls", "https+mtls"}

func WellKnownURLFromBase(baseURL string) (string, error) {
	normalized := strings.TrimSpace(baseURL)
	if normalized == "" {
		return "", ValidationError("base_url is required")
	}
	if strings.HasSuffix(normalized, DefaultWellKnownPath) {
		return normalized, nil
	}
	return strings.TrimRight(normalized, "/") + DefaultWellKnownPath, nil
}

func IdentityDocumentURLFromBase(baseURL string) (string, error) {
	normalized := strings.TrimSpace(baseURL)
	if normalized == "" {
		return "", ValidationError("base_url is required")
	}
	return strings.TrimRight(normalized, "/") + DefaultIdentityDocPath, nil
}

func inferWellKnownSecurityProfile(transports map[string]any) string {
	for _, transportName := range []string{"http", "relay"} {
		hint, ok := transports[transportName].(map[string]any)
		if !ok {
			continue
		}
		profile, ok := hint["security_profile"].(string)
		if ok && strings.TrimSpace(profile) != "" {
			return strings.TrimSpace(profile)
		}
	}
	httpHint, _ := transports["http"].(map[string]any)
	endpoint, _ := httpHint["endpoint"].(string)
	if strings.HasPrefix(endpoint, "https://") {
		return "https"
	}
	if strings.HasPrefix(endpoint, "http://") {
		return "http"
	}
	return "https"
}

func validateIdentityDocumentReference(reference string) error {
	trimmed := strings.TrimSpace(reference)
	if trimmed == "" {
		return ValidationError("identity_document URL must be absolute http(s) or root-relative path")
	}
	parsed, err := url.Parse(trimmed)
	if err == nil && parsed.Scheme != "" {
		if parsed.Scheme != "http" && parsed.Scheme != "https" {
			return ValidationError("identity_document URL must use http or https")
		}
		if strings.TrimSpace(parsed.Hostname()) == "" {
			return ValidationError("identity_document URL is missing host")
		}
		return nil
	}
	if !strings.HasPrefix(trimmed, "/") {
		return ValidationError("identity_document URL must be absolute http(s) or root-relative path")
	}
	return nil
}

func validateWellKnownTransports(transports map[string]any) error {
	for transportName, rawHint := range transports {
		hint, ok := rawHint.(map[string]any)
		if !ok {
			return ValidationError(fmt.Sprintf("Well-known transport hint %s must be an object", transportName))
		}
		if rawEndpoint, ok := hint["endpoint"]; ok {
			endpoint, ok := rawEndpoint.(string)
			if !ok {
				return ValidationError(fmt.Sprintf("Well-known transport hint %s.endpoint must be a string", transportName))
			}
			parsed, err := url.Parse(strings.TrimSpace(endpoint))
			if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || strings.TrimSpace(parsed.Hostname()) == "" {
				return ValidationError(fmt.Sprintf("Well-known transport hint %s.endpoint must be an absolute http(s) URL", transportName))
			}
		}
		if rawProfile, ok := hint["security_profile"]; ok {
			profile, ok := rawProfile.(string)
			if !ok || !slices.Contains(supportedWellKnownSecurityProfiles, profile) {
				return ValidationError(fmt.Sprintf("Well-known transport hint %s.security_profile is invalid", transportName))
			}
		}
	}
	return nil
}

type BuildWellKnownInput struct {
	IdentityDocument    map[string]any
	BaseURL             string
	IdentityDocumentURL string
	Version             string
}

func BuildWellKnownDocument(input BuildWellKnownInput) (map[string]any, error) {
	agentID, ok := input.IdentityDocument["agent_id"].(string)
	if !ok || strings.TrimSpace(agentID) == "" {
		return nil, ValidationError("identity_document.agent_id is required")
	}
	version := firstNonBlankString(input.Version, ACPVersion)
	if version != ACPVersion {
		return nil, ValidationError(fmt.Sprintf("Unsupported well-known version %s; expected %s", version, ACPVersion))
	}
	service, _ := input.IdentityDocument["service"].(map[string]any)
	if service == nil {
		service = map[string]any{}
	}
	capabilities, _ := input.IdentityDocument["capabilities"].(map[string]any)
	transports := map[string]any{}
	if directEndpoint, ok := service["direct_endpoint"].(string); ok && strings.TrimSpace(directEndpoint) != "" {
		httpHint := map[string]any{
			"endpoint": strings.TrimSpace(directEndpoint),
		}
		if httpService, ok := service["http"].(map[string]any); ok {
			if profile, ok := httpService["security_profile"].(string); ok && strings.TrimSpace(profile) != "" {
				httpHint["security_profile"] = strings.TrimSpace(profile)
			}
		}
		transports["http"] = httpHint
	}
	if relayHintsRaw, ok := service["relay_hints"].([]any); ok {
		hints := []string{}
		for _, item := range relayHintsRaw {
			hint, ok := item.(string)
			if ok && strings.TrimSpace(hint) != "" {
				hints = append(hints, strings.TrimSpace(hint))
			}
		}
		if len(hints) > 0 {
			relayHint := map[string]any{
				"endpoint": hints[0],
			}
			if len(hints) > 1 {
				relayHint["hints"] = hints
			}
			if relayService, ok := service["relay"].(map[string]any); ok {
				if profile, ok := relayService["security_profile"].(string); ok && strings.TrimSpace(profile) != "" {
					relayHint["security_profile"] = strings.TrimSpace(profile)
				}
			}
			transports["relay"] = relayHint
		}
	}
	if amqpService, ok := service["amqp"].(map[string]any); ok {
		transports["amqp"] = amqpService
	}
	if mqttService, ok := service["mqtt"].(map[string]any); ok {
		transports["mqtt"] = mqttService
	}
	identityReference := strings.TrimSpace(input.IdentityDocumentURL)
	if identityReference == "" {
		derived, err := IdentityDocumentURLFromBase(input.BaseURL)
		if err != nil {
			return nil, err
		}
		identityReference = derived
	}
	if err := validateIdentityDocumentReference(identityReference); err != nil {
		return nil, err
	}
	wellKnown := map[string]any{
		"agent_id":          strings.TrimSpace(agentID),
		"identity_document": identityReference,
		"transports":        transports,
		"version":           version,
		"security_profile":  inferWellKnownSecurityProfile(transports),
	}
	if supports, ok := capabilities["supports"].(map[string]any); ok {
		enabled := []string{}
		for key, raw := range supports {
			if asBool(raw, false) {
				enabled = append(enabled, key)
			}
		}
		slices.Sort(enabled)
		wellKnown["capabilities"] = enabled
	}
	return wellKnown, nil
}

func ParseWellKnownDocument(value any) (map[string]any, error) {
	parsed, err := ToJSONMap(value)
	if err != nil {
		return nil, err
	}
	agentID, ok := parsed["agent_id"].(string)
	if !ok || strings.TrimSpace(agentID) == "" {
		return nil, ValidationError("Well-known response missing agent_id")
	}
	version, ok := parsed["version"].(string)
	if !ok || version != ACPVersion {
		return nil, ValidationError(fmt.Sprintf("Well-known response version must be %s", ACPVersion))
	}
	identityReference, ok := parsed["identity_document"].(string)
	if !ok || strings.TrimSpace(identityReference) == "" {
		return nil, ValidationError("Well-known response identity_document must be a URL string")
	}
	if err := validateIdentityDocumentReference(identityReference); err != nil {
		return nil, err
	}
	transportsRaw, ok := parsed["transports"].(map[string]any)
	if !ok {
		return nil, ValidationError("Well-known response transports must be an object")
	}
	if err := validateWellKnownTransports(transportsRaw); err != nil {
		return nil, err
	}
	if rawProfile, ok := parsed["security_profile"]; ok {
		profile, ok := rawProfile.(string)
		if !ok || !slices.Contains(supportedWellKnownSecurityProfiles, profile) {
			return nil, ValidationError("Well-known response security_profile is invalid")
		}
	}
	return parsed, nil
}

func ResolveIdentityDocumentReference(wellKnown map[string]any, sourceURL string) (string, error) {
	reference, ok := wellKnown["identity_document"].(string)
	if !ok || strings.TrimSpace(reference) == "" {
		return "", ValidationError("Well-known response identity_document reference is invalid")
	}
	if err := validateIdentityDocumentReference(reference); err != nil {
		return "", err
	}
	if parsed, err := url.Parse(strings.TrimSpace(reference)); err == nil && parsed.Scheme != "" {
		return parsed.String(), nil
	}
	sourceParsed, err := url.Parse(sourceURL)
	if err != nil {
		return "", ValidationError(fmt.Sprintf("invalid source URL: %v", err))
	}
	resolved := sourceParsed.ResolveReference(&url.URL{Path: reference})
	return resolved.String(), nil
}
