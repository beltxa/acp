/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"encoding/json"
	"strings"
	"time"

	"github.com/google/uuid"
)

type MessageClass string

const (
	MessageSend         MessageClass = "SEND"
	MessageAck          MessageClass = "ACK"
	MessageFail         MessageClass = "FAIL"
	MessageCapabilities MessageClass = "CAPABILITIES"
	MessageCompensate   MessageClass = "COMPENSATE"
)

type DeliveryState string

const (
	StatePending      DeliveryState = "PENDING"
	StateDelivered    DeliveryState = "DELIVERED"
	StateAcknowledged DeliveryState = "ACKNOWLEDGED"
	StateFailed       DeliveryState = "FAILED"
	StateDeclined     DeliveryState = "DECLINED"
	StateExpired      DeliveryState = "EXPIRED"
)

type DeliveryMode string

const (
	DeliveryAuto   DeliveryMode = "auto"
	DeliveryDirect DeliveryMode = "direct"
	DeliveryRelay  DeliveryMode = "relay"
	DeliveryAMQP   DeliveryMode = "amqp"
	DeliveryMQTT   DeliveryMode = "mqtt"
)

type WrappedContentKey struct {
	Recipient          string `json:"recipient"`
	EphemeralPublicKey string `json:"ephemeral_public_key"`
	Nonce              string `json:"nonce"`
	Ciphertext         string `json:"ciphertext"`
}

type Envelope struct {
	ACPVersion    string       `json:"acp_version"`
	MessageClass  MessageClass `json:"message_class"`
	MessageID     string       `json:"message_id"`
	OperationID   string       `json:"operation_id"`
	Timestamp     string       `json:"timestamp"`
	ExpiresAt     string       `json:"expires_at"`
	Sender        string       `json:"sender"`
	Recipients    []string     `json:"recipients"`
	ContextID     string       `json:"context_id"`
	CryptoSuite   string       `json:"crypto_suite"`
	Namespace     *string      `json:"namespace,omitempty"`
	CorrelationID *string      `json:"correlation_id,omitempty"`
	InReplyTo     *string      `json:"in_reply_to,omitempty"`
}

type ProtectedPayload struct {
	Nonce              string              `json:"nonce"`
	Ciphertext         string              `json:"ciphertext"`
	WrappedContentKeys []WrappedContentKey `json:"wrapped_content_keys"`
	PayloadHash        string              `json:"payload_hash"`
	SignatureKID       string              `json:"signature_kid"`
	Signature          string              `json:"signature"`
}

type AcpMessage struct {
	Envelope               Envelope         `json:"envelope"`
	Protected              ProtectedPayload `json:"protected"`
	SenderIdentityDocument map[string]any   `json:"sender_identity_document,omitempty"`
}

type DeliveryOutcome struct {
	Recipient       string         `json:"recipient"`
	State           DeliveryState  `json:"state"`
	StatusCode      *int           `json:"status_code,omitempty"`
	ResponseClass   *MessageClass  `json:"response_class,omitempty"`
	ReasonCode      *string        `json:"reason_code,omitempty"`
	Detail          *string        `json:"detail,omitempty"`
	ResponseMessage map[string]any `json:"response_message,omitempty"`
}

type SendResult struct {
	OperationID string            `json:"operation_id"`
	MessageID   string            `json:"message_id"`
	MessageIDs  []string          `json:"message_ids"`
	Outcomes    []DeliveryOutcome `json:"outcomes"`
}

func ParseMessageClass(value string) *MessageClass {
	switch MessageClass(value) {
	case MessageSend, MessageAck, MessageFail, MessageCapabilities, MessageCompensate:
		parsed := MessageClass(value)
		return &parsed
	default:
		return nil
	}
}

type EnvelopeInput struct {
	Sender           string
	Recipients       []string
	MessageClass     MessageClass
	ContextID        string
	ExpiresInSeconds int
	OperationID      string
	Namespace        string
	CorrelationID    string
	InReplyTo        string
	CryptoSuite      string
}

func BuildEnvelope(input EnvelopeInput) (Envelope, error) {
	now := time.Now().UTC()
	expires := now.Add(time.Duration(maxInt(input.ExpiresInSeconds, 1)) * time.Second)
	operationID := input.OperationID
	if operationID == "" {
		operationID = uuid.NewString()
	}
	envelope := Envelope{
		ACPVersion:   ACPVersion,
		MessageClass: input.MessageClass,
		MessageID:    uuid.NewString(),
		OperationID:  operationID,
		Timestamp:    now.Format(time.RFC3339),
		ExpiresAt:    expires.Format(time.RFC3339),
		Sender:       input.Sender,
		Recipients:   append([]string{}, input.Recipients...),
		ContextID:    input.ContextID,
		CryptoSuite:  firstNonBlankString(input.CryptoSuite, DefaultCryptoSuite),
	}
	if input.CorrelationID != "" {
		envelope.CorrelationID = &input.CorrelationID
	}
	if input.InReplyTo != "" {
		envelope.InReplyTo = &input.InReplyTo
	}
	if strings.TrimSpace(input.Namespace) != "" {
		namespace := strings.TrimSpace(input.Namespace)
		envelope.Namespace = &namespace
	}
	if err := ValidateEnvelope(envelope); err != nil {
		return Envelope{}, err
	}
	return envelope, nil
}

func ValidateEnvelope(envelope Envelope) error {
	if envelope.Sender == "" {
		return ValidationError("Envelope sender is required")
	}
	if len(envelope.Recipients) == 0 {
		return ValidationError("Envelope recipients must not be empty")
	}
	parsedTimestamp, err := time.Parse(time.RFC3339, envelope.Timestamp)
	if err != nil {
		return ValidationError("Envelope timestamps must be RFC3339 strings")
	}
	parsedExpires, err := time.Parse(time.RFC3339, envelope.ExpiresAt)
	if err != nil {
		return ValidationError("Envelope timestamps must be RFC3339 strings")
	}
	if !parsedExpires.After(parsedTimestamp) {
		return ValidationError("Envelope expires_at must be after timestamp")
	}
	return nil
}

func IsExpired(envelope Envelope) bool {
	expires, err := time.Parse(time.RFC3339, envelope.ExpiresAt)
	if err != nil {
		return true
	}
	return !expires.After(time.Now().UTC())
}

func ParseAcpMessage(messageMap map[string]any) (AcpMessage, error) {
	serialized, err := json.Marshal(messageMap)
	if err != nil {
		return AcpMessage{}, ValidationError("invalid ACP message payload")
	}
	var message AcpMessage
	if err := json.Unmarshal(serialized, &message); err != nil {
		return AcpMessage{}, ValidationError("invalid ACP message payload")
	}
	if err := ValidateEnvelope(message.Envelope); err != nil {
		return AcpMessage{}, err
	}
	return message, nil
}

func MessageToMap(message AcpMessage) (map[string]any, error) {
	serialized, err := json.Marshal(message)
	if err != nil {
		return nil, ValidationError("unable to serialize ACP message")
	}
	var asMap map[string]any
	if err := json.Unmarshal(serialized, &asMap); err != nil {
		return nil, ValidationError("unable to serialize ACP message")
	}
	return asMap, nil
}

func BuildAckPayload(receivedMessageID, status string) map[string]any {
	return map[string]any{
		"status":              status,
		"received_message_id": receivedMessageID,
	}
}

func BuildFailPayload(reasonCode, detail string, retriable bool) map[string]any {
	return map[string]any{
		"reason_code": reasonCode,
		"detail":      detail,
		"retriable":   retriable,
	}
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func firstNonBlankString(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
