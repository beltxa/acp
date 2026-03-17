/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import "strings"

type OverlayHTTPResponse struct {
	StatusCode int            `json:"status_code"`
	Body       map[string]any `json:"body"`
}

type OverlayConfig struct {
	Agent              *AcpAgent
	BaseURL            string
	PassthroughHandler PassthroughHandler
}

type OverlayFrameworkRuntime struct {
	Agent           *AcpAgent
	BaseURL         string
	InboundAdapter  *OverlayInboundAdapter
	OutboundAdapter *OverlayOutboundAdapter
}

func NewOverlayFrameworkRuntime(agent *AcpAgent, baseURL string, businessHandler BusinessHandler, passthroughHandler PassthroughHandler) (*OverlayFrameworkRuntime, error) {
	if strings.TrimSpace(baseURL) == "" {
		return nil, ValidationError("base_url is required")
	}
	runtime := &OverlayFrameworkRuntime{
		Agent:           agent,
		BaseURL:         strings.TrimRight(baseURL, "/"),
		InboundAdapter:  NewOverlayInboundAdapter(agent, businessHandler, passthroughHandler),
		OutboundAdapter: NewOverlayOutboundAdapter(agent),
	}
	return runtime, nil
}

func OverlayWellKnownHeaders() map[string]any {
	return map[string]any{
		"Cache-Control": DefaultWellKnownCacheTTL,
	}
}

func (runtime *OverlayFrameworkRuntime) HandleMessageBody(body any) OverlayHTTPResponse {
	payload, err := ToJSONMap(body)
	if err != nil {
		return OverlayHTTPResponse{
			StatusCode: 400,
			Body:       InvalidOverlayRequest("Expected JSON object request body"),
		}
	}
	responseBody, err := runtime.InboundAdapter.HandleRequest(payload)
	if err != nil {
		return OverlayHTTPResponse{
			StatusCode: 400,
			Body:       InvalidOverlayRequest(err.Error()),
		}
	}
	return OverlayHTTPResponse{
		StatusCode: 200,
		Body:       responseBody,
	}
}

func (runtime *OverlayFrameworkRuntime) WellKnownDocument() (map[string]any, error) {
	return runtime.Agent.BuildWellKnownDocument(runtime.BaseURL, "")
}

func (runtime *OverlayFrameworkRuntime) IdentityDocumentPayload() map[string]any {
	return map[string]any{
		"identity_document": runtime.Agent.IdentityDocument,
	}
}

func (runtime *OverlayFrameworkRuntime) SendBusinessPayload(input OverlaySendInput) (map[string]any, error) {
	sendResult, err := runtime.OutboundAdapter.SendBusinessPayload(input)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"target":      sendResult.Target,
		"send_result": sendResult.SendResult,
	}, nil
}

func (runtime *OverlayFrameworkRuntime) SendACP(
	targetURL string,
	payload map[string]any,
	recipientAgentID string,
	context string,
	deliveryMode DeliveryMode,
	expiresInSeconds int,
) (map[string]any, error) {
	return runtime.SendBusinessPayload(OverlaySendInput{
		Payload:          payload,
		TargetBaseURL:    targetURL,
		RecipientAgentID: recipientAgentID,
		Context:          context,
		DeliveryMode:     deliveryMode,
		ExpiresInSeconds: expiresInSeconds,
	})
}

func HandleOverlayRequest(requestBody any, businessHandler BusinessHandler, config OverlayConfig) OverlayHTTPResponse {
	runtime, err := NewOverlayFrameworkRuntime(config.Agent, config.BaseURL, businessHandler, config.PassthroughHandler)
	if err != nil {
		return OverlayHTTPResponse{
			StatusCode: 400,
			Body:       InvalidOverlayRequest(err.Error()),
		}
	}
	return runtime.HandleMessageBody(requestBody)
}

type OverlayClient struct {
	Agent           *AcpAgent
	OutboundAdapter *OverlayOutboundAdapter
}

func NewOverlayClient(agent *AcpAgent) *OverlayClient {
	return &OverlayClient{
		Agent:           agent,
		OutboundAdapter: NewOverlayOutboundAdapter(agent),
	}
}

func (client *OverlayClient) SendACP(
	targetURL string,
	payload map[string]any,
	recipientAgentID string,
	context string,
	deliveryMode DeliveryMode,
	expiresInSeconds int,
) (map[string]any, error) {
	sendResult, err := client.OutboundAdapter.SendBusinessPayload(OverlaySendInput{
		Payload:          payload,
		TargetBaseURL:    targetURL,
		RecipientAgentID: recipientAgentID,
		Context:          context,
		DeliveryMode:     deliveryMode,
		ExpiresInSeconds: expiresInSeconds,
	})
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"target":      sendResult.Target,
		"send_result": sendResult.SendResult,
	}, nil
}
