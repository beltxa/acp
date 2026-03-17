/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

const (
	DefaultAMQPExchange     = "acp.exchange"
	DefaultAMQPExchangeType = "direct"
)

type AMQPMessageHandler func(message map[string]any) bool

type AmqpTransportClient struct {
	BrokerURL      string
	Exchange       string
	ExchangeType   string
	TimeoutSeconds int
}

var amqpAgentPattern = regexp.MustCompile(`^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$`)

func NewAmqpTransportClient(brokerURL, exchange, exchangeType string, timeoutSeconds int) (*AmqpTransportClient, error) {
	if strings.TrimSpace(brokerURL) == "" {
		return nil, InvalidArgument("broker_url must be provided")
	}
	if strings.TrimSpace(exchange) == "" {
		exchange = DefaultAMQPExchange
	}
	if strings.TrimSpace(exchangeType) == "" {
		exchangeType = DefaultAMQPExchangeType
	}
	return &AmqpTransportClient{
		BrokerURL:      strings.TrimSpace(brokerURL),
		Exchange:       strings.TrimSpace(exchange),
		ExchangeType:   strings.TrimSpace(exchangeType),
		TimeoutSeconds: maxInt(timeoutSeconds, 1),
	}, nil
}

func AMQPAgentIdentifierToken(agentID string) (string, error) {
	matches := amqpAgentPattern.FindStringSubmatch(agentID)
	if len(matches) == 0 {
		return "", ValidationError(fmt.Sprintf("Invalid agent identifier: %s", agentID))
	}
	var name string
	var domain string
	for index, group := range amqpAgentPattern.SubexpNames() {
		switch group {
		case "name":
			name = matches[index]
		case "domain":
			domain = matches[index]
		}
	}
	base := name
	if domain != "" {
		base = name + "." + domain
	}
	var normalized strings.Builder
	for _, char := range base {
		if (char >= 'a' && char <= 'z') ||
			(char >= 'A' && char <= 'Z') ||
			(char >= '0' && char <= '9') ||
			char == '.' || char == '_' || char == '-' {
			normalized.WriteRune(char)
		} else {
			normalized.WriteRune('.')
		}
	}
	cleanedParts := []string{}
	for _, part := range strings.Split(normalized.String(), ".") {
		part = strings.TrimSpace(part)
		if part != "" {
			cleanedParts = append(cleanedParts, part)
		}
	}
	if len(cleanedParts) == 0 {
		return "unknown", nil
	}
	return strings.Join(cleanedParts, "."), nil
}

func AMQPQueueNameForAgent(agentID string) (string, error) {
	token, err := AMQPAgentIdentifierToken(agentID)
	if err != nil {
		return "", err
	}
	return "acp.agent." + token, nil
}

func AMQPRoutingKeyForAgent(agentID string) (string, error) {
	token, err := AMQPAgentIdentifierToken(agentID)
	if err != nil {
		return "", err
	}
	return "agent." + token, nil
}

func BuildAMQPServiceHint(agentID, brokerURL, exchange string) (map[string]any, error) {
	queue, err := AMQPQueueNameForAgent(agentID)
	if err != nil {
		return nil, err
	}
	routingKey, err := AMQPRoutingKeyForAgent(agentID)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(exchange) == "" {
		exchange = DefaultAMQPExchange
	}
	return map[string]any{
		"broker_url":  strings.TrimSpace(brokerURL),
		"exchange":    strings.TrimSpace(exchange),
		"queue":       queue,
		"routing_key": routingKey,
	}, nil
}

func AMQPMetadataHeaders(message map[string]any) map[string]string {
	out := map[string]string{}
	envelope, _ := message["envelope"].(map[string]any)
	for source, destination := range map[string]string{
		"acp_version":   "acp_version",
		"message_class": "acp_message_class",
		"message_id":    "acp_message_id",
		"operation_id":  "acp_operation_id",
		"sender":        "acp_sender",
	} {
		raw, _ := envelope[source].(string)
		trimmed := strings.TrimSpace(raw)
		if trimmed != "" {
			out[destination] = trimmed
		}
	}
	return out
}

func pickServiceString(service map[string]any, key string, fallback string) string {
	if service == nil {
		return fallback
	}
	value, ok := service[key].(string)
	if ok && strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	return fallback
}

func (client *AmqpTransportClient) Publish(message map[string]any, recipientAgentID string, service map[string]any) error {
	brokerURL := pickServiceString(service, "broker_url", client.BrokerURL)
	exchange := pickServiceString(service, "exchange", client.Exchange)
	queue := ""
	if value, ok := service["queue"].(string); ok && strings.TrimSpace(value) != "" {
		queue = strings.TrimSpace(value)
	} else {
		derived, err := AMQPQueueNameForAgent(recipientAgentID)
		if err != nil {
			return err
		}
		queue = derived
	}
	routingKey := ""
	if value, ok := service["routing_key"].(string); ok && strings.TrimSpace(value) != "" {
		routingKey = strings.TrimSpace(value)
	} else {
		derived, err := AMQPRoutingKeyForAgent(recipientAgentID)
		if err != nil {
			return err
		}
		routingKey = derived
	}
	body, err := json.Marshal(message)
	if err != nil {
		return TransportError(fmt.Sprintf("unable to serialize AMQP payload: %v", err))
	}
	connection, err := amqp.DialConfig(brokerURL, amqp.Config{
		Heartbeat: time.Duration(client.TimeoutSeconds) * time.Second,
	})
	if err != nil {
		return TransportError(fmt.Sprintf("amqp publish failed: %v", err))
	}
	defer connection.Close()
	channel, err := connection.Channel()
	if err != nil {
		return TransportError(fmt.Sprintf("amqp publish failed: %v", err))
	}
	defer channel.Close()
	if err := channel.ExchangeDeclare(exchange, client.ExchangeType, true, false, false, false, nil); err != nil {
		return TransportError(fmt.Sprintf("amqp publish failed: %v", err))
	}
	if _, err := channel.QueueDeclare(queue, true, false, false, false, nil); err != nil {
		return TransportError(fmt.Sprintf("amqp publish failed: %v", err))
	}
	if err := channel.QueueBind(queue, routingKey, exchange, false, nil); err != nil {
		return TransportError(fmt.Sprintf("amqp publish failed: %v", err))
	}
	headers := amqp.Table{}
	for key, value := range AMQPMetadataHeaders(message) {
		headers[key] = value
	}
	if err := channel.PublishWithContext(
		context.Background(),
		exchange,
		routingKey,
		false,
		false,
		amqp.Publishing{
			ContentType:  "application/json",
			DeliveryMode: amqp.Persistent,
			Body:         body,
			Headers:      headers,
		},
	); err != nil {
		return TransportError(fmt.Sprintf("amqp publish failed: %v", err))
	}
	return nil
}

func (client *AmqpTransportClient) Consume(agentID string, handler AMQPMessageHandler, service map[string]any, maxMessages int) (int, error) {
	brokerURL := pickServiceString(service, "broker_url", client.BrokerURL)
	exchange := pickServiceString(service, "exchange", client.Exchange)
	queue := pickServiceString(service, "queue", "")
	if queue == "" {
		derived, err := AMQPQueueNameForAgent(agentID)
		if err != nil {
			return 0, err
		}
		queue = derived
	}
	routingKey := pickServiceString(service, "routing_key", "")
	if routingKey == "" {
		derived, err := AMQPRoutingKeyForAgent(agentID)
		if err != nil {
			return 0, err
		}
		routingKey = derived
	}
	if maxMessages <= 0 {
		maxMessages = int(^uint(0) >> 1)
	}
	connection, err := amqp.DialConfig(brokerURL, amqp.Config{
		Heartbeat: time.Duration(client.TimeoutSeconds) * time.Second,
	})
	if err != nil {
		return 0, TransportError(fmt.Sprintf("amqp consume failed: %v", err))
	}
	defer connection.Close()
	channel, err := connection.Channel()
	if err != nil {
		return 0, TransportError(fmt.Sprintf("amqp consume failed: %v", err))
	}
	defer channel.Close()
	if err := channel.ExchangeDeclare(exchange, client.ExchangeType, true, false, false, false, nil); err != nil {
		return 0, TransportError(fmt.Sprintf("amqp consume failed: %v", err))
	}
	if _, err := channel.QueueDeclare(queue, true, false, false, false, nil); err != nil {
		return 0, TransportError(fmt.Sprintf("amqp consume failed: %v", err))
	}
	if err := channel.QueueBind(queue, routingKey, exchange, false, nil); err != nil {
		return 0, TransportError(fmt.Sprintf("amqp consume failed: %v", err))
	}
	processed := 0
	for processed < maxMessages {
		delivery, ok, err := channel.Get(queue, false)
		if err != nil {
			return processed, TransportError(fmt.Sprintf("amqp consume failed: %v", err))
		}
		if !ok {
			break
		}
		shouldAck := false
		var parsed map[string]any
		if err := json.Unmarshal(delivery.Body, &parsed); err == nil && parsed != nil {
			shouldAck = handler(parsed)
		}
		if shouldAck {
			_ = delivery.Ack(false)
		} else {
			_ = delivery.Nack(false, true)
		}
		processed++
	}
	return processed, nil
}
