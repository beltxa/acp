/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type TransportResponse struct {
	StatusCode int
	Body       map[string]any
	RawBody    string
}

type TransportClient struct {
	timeoutSeconds int
	policy         HTTPSecurityPolicy
	httpClient     *http.Client
	defaultAuth    *AuthConfig
}

func NewTransportClient(timeoutSeconds int, policy HTTPSecurityPolicy) (*TransportClient, error) {
	return NewTransportClientWithAuth(timeoutSeconds, policy, nil)
}

func NewTransportClientWithAuth(timeoutSeconds int, policy HTTPSecurityPolicy, auth *AuthConfig) (*TransportClient, error) {
	normalizedAuth, err := NormalizeAuthConfig(auth)
	if err != nil {
		return nil, err
	}
	httpClient, err := BuildHTTPClient(policy, timeoutSeconds)
	if err != nil {
		return nil, err
	}
	return &TransportClient{
		timeoutSeconds: maxInt(timeoutSeconds, 1),
		policy:         policy,
		httpClient:     httpClient,
		defaultAuth:    normalizedAuth,
	}, nil
}

func (client *TransportClient) PostJSON(rawURL string, body map[string]any) (*TransportResponse, error) {
	return client.PostJSONWithConfig(rawURL, body, nil)
}

func (client *TransportClient) PostJSONWithConfig(rawURL string, body map[string]any, config *TransportConfig) (*TransportResponse, error) {
	auth := client.defaultAuth
	if config != nil && config.Auth != nil {
		normalizedAuth, err := NormalizeAuthConfig(config.Auth)
		if err != nil {
			return nil, err
		}
		auth = normalizedAuth
	}
	effectivePolicy := client.policy
	headers, err := httpAuthHeaders(auth)
	if err != nil {
		return nil, err
	}
	if auth != nil && auth.Type == "mtls" {
		certFile, err := RequireAuthParameter(auth, "cert_path", "mTLS auth")
		if err != nil {
			return nil, err
		}
		keyFile, err := RequireAuthParameter(auth, "key_path", "mTLS auth")
		if err != nil {
			return nil, err
		}
		effectivePolicy.MTLSEnabled = true
		effectivePolicy.CertFile = certFile
		effectivePolicy.KeyFile = keyFile
		if caPath := strings.TrimSpace(auth.Parameters["ca_path"]); caPath != "" {
			effectivePolicy.CAFile = caPath
		}
	}
	if _, err := ValidateHTTPURL(rawURL, effectivePolicy.AllowInsecureHTTP, effectivePolicy.MTLSEnabled, "HTTP transport request"); err != nil {
		return nil, err
	}
	data, err := json.Marshal(body)
	if err != nil {
		return nil, TransportError(fmt.Sprintf("unable to encode JSON request: %v", err))
	}
	request, err := http.NewRequest(http.MethodPost, rawURL, bytes.NewReader(data))
	if err != nil {
		return nil, TransportError(fmt.Sprintf("unable to build HTTP request: %v", err))
	}
	request.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	httpClient := client.httpClient
	if auth != nil && auth.Type == "mtls" {
		httpClient, err = BuildHTTPClient(effectivePolicy, client.timeoutSeconds)
		if err != nil {
			return nil, err
		}
	}
	response, err := httpClient.Do(request)
	if err != nil {
		return nil, TransportError(fmt.Sprintf("HTTP request failed: %v", err))
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, TransportError(fmt.Sprintf("unable to read HTTP response: %v", err))
	}
	transportResponse := &TransportResponse{
		StatusCode: response.StatusCode,
		RawBody:    string(raw),
	}
	parsed, err := ParseJSONMap(raw)
	if err == nil {
		transportResponse.Body = parsed
	}
	return transportResponse, nil
}

func (client *TransportClient) SendToRelay(relayURL string, message AcpMessage) (map[string]any, error) {
	return client.SendToRelayWithConfig(relayURL, message, nil)
}

func (client *TransportClient) SendToRelayWithConfig(relayURL string, message AcpMessage, config *TransportConfig) (map[string]any, error) {
	messageMap, err := MessageToMap(message)
	if err != nil {
		return nil, err
	}
	relayEndpoint := strings.TrimRight(relayURL, "/") + "/messages"
	response, err := client.PostJSONWithConfig(relayEndpoint, messageMap, config)
	if err != nil {
		return nil, err
	}
	if response.StatusCode != http.StatusOK {
		return nil, TransportError(fmt.Sprintf("Relay returned HTTP %d for message %s", response.StatusCode, message.Envelope.MessageID))
	}
	if response.Body == nil {
		return nil, TransportError("Relay returned non-JSON response")
	}
	return response.Body, nil
}

func httpAuthHeaders(auth *AuthConfig) (map[string]string, error) {
	headers := map[string]string{}
	if auth == nil || auth.Type == "none" || auth.Type == "mtls" {
		return headers, nil
	}
	switch auth.Type {
	case "bearer":
		token, err := RequireAuthParameter(auth, "token", "Bearer auth")
		if err != nil {
			return nil, err
		}
		headers["Authorization"] = "Bearer " + token
	case "basic":
		username, err := RequireAuthParameter(auth, "username", "Basic auth")
		if err != nil {
			return nil, err
		}
		password, err := RequireAuthParameter(auth, "password", "Basic auth")
		if err != nil {
			return nil, err
		}
		headers["Authorization"] = BasicAuthorizationHeader(username, password)
	case "custom":
		header := strings.TrimSpace(auth.Parameters["header"])
		value := strings.TrimSpace(auth.Parameters["value"])
		scheme := strings.TrimSpace(auth.Parameters["scheme"])
		if header != "" {
			if value == "" {
				return nil, ValidationError("Custom auth requires auth.parameters.value when header is set")
			}
			headers[header] = value
			return headers, nil
		}
		if scheme != "" {
			if value == "" {
				return nil, ValidationError("Custom auth requires auth.parameters.value when scheme is set")
			}
			headers["Authorization"] = scheme + " " + value
			return headers, nil
		}
		return nil, ValidationError(
			"Custom auth requires either parameters.header + parameters.value or parameters.scheme + parameters.value",
		)
	default:
		return nil, ValidationError(fmt.Sprintf("HTTP transport does not support auth type: %s", auth.Type))
	}
	return headers, nil
}
