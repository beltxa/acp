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
}

func NewTransportClient(timeoutSeconds int, policy HTTPSecurityPolicy) (*TransportClient, error) {
	httpClient, err := BuildHTTPClient(policy, timeoutSeconds)
	if err != nil {
		return nil, err
	}
	return &TransportClient{
		timeoutSeconds: maxInt(timeoutSeconds, 1),
		policy:         policy,
		httpClient:     httpClient,
	}, nil
}

func (client *TransportClient) PostJSON(rawURL string, body map[string]any) (*TransportResponse, error) {
	if _, err := ValidateHTTPURL(rawURL, client.policy.AllowInsecureHTTP, client.policy.MTLSEnabled, "HTTP transport request"); err != nil {
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
	response, err := client.httpClient.Do(request)
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
	messageMap, err := MessageToMap(message)
	if err != nil {
		return nil, err
	}
	relayEndpoint := strings.TrimRight(relayURL, "/") + "/messages"
	response, err := client.PostJSON(relayEndpoint, messageMap)
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
