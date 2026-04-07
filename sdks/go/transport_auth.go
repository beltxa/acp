/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"encoding/base64"
	"fmt"
	"strings"
)

type AuthConfig struct {
	Type       string            `json:"type"`
	Parameters map[string]string `json:"parameters,omitempty"`
}

type TransportConfig struct {
	Protocol string      `json:"protocol"`
	Endpoint string      `json:"endpoint"`
	Auth     *AuthConfig `json:"auth,omitempty"`
}

var supportedAuthTypes = map[string]struct{}{
	"none":              {},
	"bearer":            {},
	"basic":             {},
	"mtls":              {},
	"username_password": {},
	"custom":            {},
}

func normalizeAuthType(value string) (string, error) {
	normalized := strings.ToLower(strings.TrimSpace(value))
	if normalized == "" {
		normalized = "none"
	}
	if _, ok := supportedAuthTypes[normalized]; !ok {
		return "", ValidationError(fmt.Sprintf("Unsupported auth type: %s", value))
	}
	return normalized, nil
}

func NormalizeAuthConfig(auth *AuthConfig) (*AuthConfig, error) {
	if auth == nil {
		return nil, nil
	}
	authType, err := normalizeAuthType(auth.Type)
	if err != nil {
		return nil, err
	}
	parameters := map[string]string{}
	for key, value := range auth.Parameters {
		trimmedKey := strings.TrimSpace(key)
		if trimmedKey == "" {
			continue
		}
		parameters[trimmedKey] = strings.TrimSpace(value)
	}
	return &AuthConfig{
		Type:       authType,
		Parameters: parameters,
	}, nil
}

func AuthConfigFromAny(value any) (*AuthConfig, error) {
	if value == nil {
		return nil, nil
	}
	if auth, ok := value.(*AuthConfig); ok {
		return NormalizeAuthConfig(auth)
	}
	raw, ok := value.(map[string]any)
	if !ok {
		return nil, ValidationError("transport auth must be an object with fields: type, parameters")
	}
	authType := "none"
	if parsedType, ok := raw["type"].(string); ok {
		authType = parsedType
	}
	parameters := map[string]string{}
	switch typed := raw["parameters"].(type) {
	case nil:
	case map[string]string:
		for key, item := range typed {
			parameters[key] = item
		}
	case map[string]any:
		for key, item := range typed {
			if item == nil {
				continue
			}
			parameters[key] = fmt.Sprint(item)
		}
	default:
		return nil, ValidationError("transport auth.parameters must be an object")
	}
	return NormalizeAuthConfig(&AuthConfig{
		Type:       authType,
		Parameters: parameters,
	})
}

func AuthConfigToMap(auth *AuthConfig) map[string]any {
	if auth == nil {
		return nil
	}
	parameters := map[string]any{}
	for key, value := range auth.Parameters {
		parameters[key] = value
	}
	return map[string]any{
		"type":       auth.Type,
		"parameters": parameters,
	}
}

func RequireAuthParameter(auth *AuthConfig, key, context string) (string, error) {
	if auth == nil {
		return "", ValidationError(fmt.Sprintf("%s requires auth.parameters.%s", context, key))
	}
	value := strings.TrimSpace(auth.Parameters[key])
	if value == "" {
		return "", ValidationError(fmt.Sprintf("%s requires auth.parameters.%s", context, key))
	}
	return value, nil
}

func BasicAuthorizationHeader(username, password string) string {
	token := base64.StdEncoding.EncodeToString([]byte(username + ":" + password))
	return "Basic " + token
}
