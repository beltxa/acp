/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
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
	Auth           *AuthConfig
}

var amqpAgentPattern = regexp.MustCompile(`^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$`)

func NewAmqpTransportClient(brokerURL, exchange, exchangeType string, timeoutSeconds int) (*AmqpTransportClient, error) {
	return NewAmqpTransportClientWithAuth(brokerURL, exchange, exchangeType, timeoutSeconds, nil)
}

func NewAmqpTransportClientWithAuth(
	brokerURL, exchange, exchangeType string, timeoutSeconds int, auth *AuthConfig,
) (*AmqpTransportClient, error) {
	if strings.TrimSpace(brokerURL) == "" {
		return nil, InvalidArgument("broker_url must be provided")
	}
	if strings.TrimSpace(exchange) == "" {
		exchange = DefaultAMQPExchange
	}
	if strings.TrimSpace(exchangeType) == "" {
		exchangeType = DefaultAMQPExchangeType
	}
	normalizedAuth, err := NormalizeAuthConfig(auth)
	if err != nil {
		return nil, err
	}
	return &AmqpTransportClient{
		BrokerURL:      strings.TrimSpace(brokerURL),
		Exchange:       strings.TrimSpace(exchange),
		ExchangeType:   strings.TrimSpace(exchangeType),
		TimeoutSeconds: maxInt(timeoutSeconds, 1),
		Auth:           normalizedAuth,
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
	return BuildAMQPServiceHintWithAuth(agentID, brokerURL, exchange, nil)
}

func BuildAMQPServiceHintWithAuth(agentID, brokerURL, exchange string, auth *AuthConfig) (map[string]any, error) {
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
	normalizedAuth, err := NormalizeAuthConfig(auth)
	if err != nil {
		return nil, err
	}
	hint := map[string]any{
		"broker_url":  strings.TrimSpace(brokerURL),
		"exchange":    strings.TrimSpace(exchange),
		"queue":       queue,
		"routing_key": routingKey,
	}
	if authMap := AuthConfigToMap(normalizedAuth); authMap != nil {
		hint["auth"] = authMap
	}
	return hint, nil
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
	auth, err := effectiveServiceAuth(service, client.Auth)
	if err != nil {
		return err
	}
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
	connection, err := dialAMQPWithAuth(brokerURL, client.TimeoutSeconds, auth)
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
	auth, err := effectiveServiceAuth(service, client.Auth)
	if err != nil {
		return 0, err
	}
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
	connection, err := dialAMQPWithAuth(brokerURL, client.TimeoutSeconds, auth)
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

func effectiveServiceAuth(service map[string]any, fallback *AuthConfig) (*AuthConfig, error) {
	if service != nil {
		if rawAuth, ok := service["auth"]; ok && rawAuth != nil {
			return AuthConfigFromAny(rawAuth)
		}
	}
	return NormalizeAuthConfig(fallback)
}

func dialAMQPWithAuth(brokerURL string, timeoutSeconds int, auth *AuthConfig) (*amqp.Connection, error) {
	config := amqp.Config{
		Heartbeat: time.Duration(timeoutSeconds) * time.Second,
	}
	effectiveURL := brokerURL
	if auth != nil {
		switch auth.Type {
		case "none":
		case "username_password":
			username, err := RequireAuthParameter(auth, "username", "AMQP username_password auth")
			if err != nil {
				return nil, err
			}
			password, err := RequireAuthParameter(auth, "password", "AMQP username_password auth")
			if err != nil {
				return nil, err
			}
			config.SASL = []amqp.Authentication{&amqp.PlainAuth{Username: username, Password: password}}
		case "custom":
			username := strings.TrimSpace(auth.Parameters["username"])
			password := strings.TrimSpace(auth.Parameters["password"])
			if username != "" {
				config.SASL = []amqp.Authentication{&amqp.PlainAuth{Username: username, Password: password}}
			}
		case "mtls":
			tlsConfig, err := buildAMQPTLSConfig(auth, true)
			if err != nil {
				return nil, err
			}
			config.TLSClientConfig = tlsConfig
			effectiveURL = ensureAMQPSScheme(effectiveURL)
		default:
			return nil, ValidationError(fmt.Sprintf("AMQP transport does not support auth type: %s", auth.Type))
		}
		if auth.Type == "custom" {
			if certPath := strings.TrimSpace(auth.Parameters["cert_path"]); certPath != "" {
				tlsConfig, err := buildAMQPTLSConfig(auth, false)
				if err != nil {
					return nil, err
				}
				config.TLSClientConfig = tlsConfig
				effectiveURL = ensureAMQPSScheme(effectiveURL)
			}
		}
	}
	return amqp.DialConfig(effectiveURL, config)
}

func buildAMQPTLSConfig(auth *AuthConfig, requireClientCertificate bool) (*tls.Config, error) {
	tlsConfig := &tls.Config{MinVersion: tls.VersionTLS12}
	if caPath := strings.TrimSpace(auth.Parameters["ca_path"]); caPath != "" {
		data, err := os.ReadFile(caPath)
		if err != nil {
			return nil, ValidationError(fmt.Sprintf("unable to read auth.parameters.ca_path: %v", err))
		}
		pool := x509.NewCertPool()
		if ok := pool.AppendCertsFromPEM(data); !ok {
			return nil, ValidationError("unable to parse CA bundle from auth.parameters.ca_path")
		}
		tlsConfig.RootCAs = pool
	}
	certPath := strings.TrimSpace(auth.Parameters["cert_path"])
	keyPath := strings.TrimSpace(auth.Parameters["key_path"])
	if requireClientCertificate {
		if certPath == "" || keyPath == "" {
			return nil, ValidationError("AMQP mTLS auth requires auth.parameters.cert_path and auth.parameters.key_path")
		}
	}
	if certPath != "" && keyPath != "" {
		certificate, err := tls.LoadX509KeyPair(certPath, keyPath)
		if err != nil {
			return nil, ValidationError(fmt.Sprintf("unable to load AMQP client certificate: %v", err))
		}
		tlsConfig.Certificates = []tls.Certificate{certificate}
	}
	return tlsConfig, nil
}

func ensureAMQPSScheme(rawURL string) string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	if parsed.Scheme == "amqp" {
		parsed.Scheme = "amqps"
	}
	return parsed.String()
}
