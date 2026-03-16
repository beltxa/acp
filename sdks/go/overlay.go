package acp

import (
	"strings"
)

type OverlayTarget struct {
	AgentID             string `json:"agent_id"`
	BaseURL             string `json:"base_url"`
	WellKnownURL        string `json:"well_known_url"`
	IdentityDocumentURL string `json:"identity_document_url"`
}

type OverlaySendResult struct {
	Target     *OverlayTarget `json:"target,omitempty"`
	SendResult SendResult     `json:"send_result"`
}

type BusinessHandler func(payload map[string]any) map[string]any
type PassthroughHandler func(payload map[string]any) map[string]any

func IsACPHTTPMessage(body map[string]any) bool {
	if body == nil {
		return false
	}
	_, hasEnvelope := body["envelope"].(map[string]any)
	_, hasProtected := body["protected"].(map[string]any)
	return hasEnvelope && hasProtected
}

func InvalidOverlayRequest(detail string) map[string]any {
	return map[string]any{
		"mode":             "invalid",
		"state":            "FAILED",
		"reason_code":      string(FailPolicyRejected),
		"detail":           detail,
		"response_message": nil,
	}
}

type OverlayInboundAdapter struct {
	Agent              *AcpAgent
	businessHandler    BusinessHandler
	passthroughHandler PassthroughHandler
}

func NewOverlayInboundAdapter(agent *AcpAgent, businessHandler BusinessHandler, passthroughHandler PassthroughHandler) *OverlayInboundAdapter {
	return &OverlayInboundAdapter{
		Agent:              agent,
		businessHandler:    businessHandler,
		passthroughHandler: passthroughHandler,
	}
}

func (adapter *OverlayInboundAdapter) HandleRequest(body map[string]any) (map[string]any, error) {
	if !IsACPHTTPMessage(body) {
		if adapter.passthroughHandler != nil {
			payload := adapter.passthroughHandler(body)
			if payload == nil {
				payload = map[string]any{}
			}
			return map[string]any{
				"mode":    "passthrough",
				"payload": payload,
			}, nil
		}
		return nil, ValidationError("Request is not an ACP message and no passthrough_handler is configured")
	}
	inbound := adapter.Agent.Receive(body, func(payload map[string]any, _ Envelope) map[string]any {
		if adapter.businessHandler == nil {
			return nil
		}
		return adapter.businessHandler(payload)
	})
	return map[string]any{
		"mode":             "acp",
		"acp_result":       inbound,
		"state":            inbound.State,
		"reason_code":      nullableString(inbound.ReasonCode),
		"detail":           nullableString(inbound.Detail),
		"response_message": inbound.ResponseMessage,
	}, nil
}

type OverlayOutboundAdapter struct {
	Agent *AcpAgent
}

func NewOverlayOutboundAdapter(agent *AcpAgent) *OverlayOutboundAdapter {
	return &OverlayOutboundAdapter{Agent: agent}
}

func (adapter *OverlayOutboundAdapter) ResolveTarget(targetBaseURL string, expectedAgentID string) (*OverlayTarget, error) {
	resolved, err := adapter.Agent.ResolveWellKnown(targetBaseURL, expectedAgentID)
	if err != nil {
		return nil, err
	}
	wellKnown, _ := resolved["well_known"].(map[string]any)
	identityDocument, _ := resolved["identity_document"].(map[string]any)
	agentID, _ := identityDocument["agent_id"].(string)
	if strings.TrimSpace(agentID) == "" {
		return nil, ValidationError("Resolved well-known metadata did not include a valid identity_document.agent_id")
	}
	identityDocumentURL, _ := wellKnown["identity_document"].(string)
	if strings.TrimSpace(identityDocumentURL) == "" {
		return nil, ValidationError("Resolved well-known metadata did not include a valid identity_document URL")
	}
	wellKnownURL, _ := resolved["well_known_url"].(string)
	return &OverlayTarget{
		AgentID:             agentID,
		BaseURL:             strings.TrimRight(targetBaseURL, "/"),
		WellKnownURL:        wellKnownURL,
		IdentityDocumentURL: identityDocumentURL,
	}, nil
}

type OverlaySendInput struct {
	Payload          map[string]any
	TargetBaseURL    string
	RecipientAgentID string
	Context          string
	DeliveryMode     DeliveryMode
	ExpiresInSeconds int
}

func (adapter *OverlayOutboundAdapter) SendBusinessPayload(input OverlaySendInput) (*OverlaySendResult, error) {
	var target *OverlayTarget
	recipientAgentID := strings.TrimSpace(input.RecipientAgentID)
	if strings.TrimSpace(input.TargetBaseURL) != "" {
		resolved, err := adapter.ResolveTarget(input.TargetBaseURL, recipientAgentID)
		if err != nil {
			return nil, err
		}
		target = resolved
		if recipientAgentID == "" {
			recipientAgentID = resolved.AgentID
		}
	}
	if recipientAgentID == "" {
		return nil, ValidationError("send_business_payload requires recipient_agent_id or target_base_url for well-known bootstrap")
	}
	sendResult, err := adapter.Agent.Send(
		[]string{recipientAgentID},
		coalesceMap(input.Payload, map[string]any{}),
		input.Context,
		MessageSend,
		maxInt(input.ExpiresInSeconds, 300),
		"",
		"",
		input.DeliveryMode,
	)
	if err != nil {
		return nil, err
	}
	return &OverlaySendResult{
		Target:     target,
		SendResult: sendResult,
	}, nil
}
