package acp

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

const (
	DefaultMQTTQoS         = 1
	DefaultMQTTTopicPrefix = "acp/agent"
)

type MQTTMessageHandler func(message map[string]any) bool

type MqttTransportClient struct {
	BrokerURL        string
	QoS              int
	TopicPrefix      string
	TimeoutSeconds   int
	KeepaliveSeconds int
}

var mqttAgentPattern = regexp.MustCompile(`^agent:(?P<name>[^@]+)(?:@(?P<domain>.+))?$`)

func NewMqttTransportClient(brokerURL string, qos int, topicPrefix string, timeoutSeconds int, keepaliveSeconds int) (*MqttTransportClient, error) {
	if strings.TrimSpace(brokerURL) == "" {
		return nil, InvalidArgument("broker_url must be provided")
	}
	if strings.TrimSpace(topicPrefix) == "" {
		topicPrefix = DefaultMQTTTopicPrefix
	}
	return &MqttTransportClient{
		BrokerURL:        strings.TrimSpace(brokerURL),
		QoS:              clampMQTTQoS(qos),
		TopicPrefix:      strings.TrimRight(strings.TrimSpace(topicPrefix), "/"),
		TimeoutSeconds:   maxInt(timeoutSeconds, 1),
		KeepaliveSeconds: maxInt(keepaliveSeconds, 5),
	}, nil
}

func clampMQTTQoS(qos int) int {
	if qos < 0 {
		return 0
	}
	if qos > 2 {
		return 2
	}
	return qos
}

func MQTTAgentIdentifierToken(agentID string) (string, error) {
	matches := mqttAgentPattern.FindStringSubmatch(agentID)
	if len(matches) == 0 {
		return "", ValidationError(fmt.Sprintf("Invalid agent identifier: %s", agentID))
	}
	var name, domain string
	for index, group := range mqttAgentPattern.SubexpNames() {
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
	for _, char := range strings.ToLower(base) {
		if (char >= 'a' && char <= 'z') ||
			(char >= '0' && char <= '9') ||
			char == '.' || char == '_' || char == '-' {
			normalized.WriteRune(char)
		} else {
			normalized.WriteRune('.')
		}
	}
	parts := []string{}
	for _, part := range strings.Split(normalized.String(), ".") {
		part = strings.TrimSpace(part)
		if part != "" {
			parts = append(parts, part)
		}
	}
	if len(parts) == 0 {
		return "unknown", nil
	}
	return strings.Join(parts, "."), nil
}

func MQTTTopicForAgent(agentID string, topicPrefix string) (string, error) {
	token, err := MQTTAgentIdentifierToken(agentID)
	if err != nil {
		return "", err
	}
	prefix := strings.TrimSpace(topicPrefix)
	if prefix == "" {
		prefix = DefaultMQTTTopicPrefix
	}
	return strings.TrimRight(prefix, "/") + "/" + token, nil
}

func BuildMQTTServiceHint(agentID, brokerURL, topic string, qos int, topicPrefix string) (map[string]any, error) {
	if strings.TrimSpace(topic) == "" {
		derived, err := MQTTTopicForAgent(agentID, topicPrefix)
		if err != nil {
			return nil, err
		}
		topic = derived
	}
	return map[string]any{
		"broker_url": strings.TrimSpace(brokerURL),
		"topic":      strings.TrimSpace(topic),
		"qos":        clampMQTTQoS(qos),
	}, nil
}

func MQTTMetadataProperties(message map[string]any) map[string]string {
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

func mqttStringValue(service map[string]any, key string, fallback string) string {
	if service == nil {
		return fallback
	}
	value, ok := service[key].(string)
	if ok && strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	return fallback
}

func mqttNumberValue(service map[string]any, key string, fallback int) int {
	if service == nil {
		return fallback
	}
	switch typed := service[key].(type) {
	case int:
		return clampMQTTQoS(typed)
	case float64:
		return clampMQTTQoS(int(typed))
	default:
		return fallback
	}
}

func (client *MqttTransportClient) connect(brokerURL string) (mqtt.Client, error) {
	options := mqtt.NewClientOptions()
	options.AddBroker(brokerURL)
	options.SetProtocolVersion(5)
	options.SetKeepAlive(time.Duration(client.KeepaliveSeconds) * time.Second)
	options.SetConnectTimeout(time.Duration(client.TimeoutSeconds) * time.Second)
	options.SetAutoReconnect(false)
	mqttClient := mqtt.NewClient(options)
	token := mqttClient.Connect()
	if !token.WaitTimeout(time.Duration(client.TimeoutSeconds) * time.Second) {
		return nil, TransportError("mqtt connect timeout")
	}
	if token.Error() != nil {
		return nil, TransportError(fmt.Sprintf("mqtt connect failed: %v", token.Error()))
	}
	return mqttClient, nil
}

func (client *MqttTransportClient) Publish(message map[string]any, recipientAgentID string, service map[string]any) error {
	brokerURL := mqttStringValue(service, "broker_url", client.BrokerURL)
	topic := mqttStringValue(service, "topic", "")
	if topic == "" {
		derived, err := MQTTTopicForAgent(recipientAgentID, client.TopicPrefix)
		if err != nil {
			return err
		}
		topic = derived
	}
	qos := mqttNumberValue(service, "qos", client.QoS)
	body, err := json.Marshal(message)
	if err != nil {
		return TransportError(fmt.Sprintf("unable to serialize MQTT payload: %v", err))
	}
	mqttClient, err := client.connect(brokerURL)
	if err != nil {
		return err
	}
	defer mqttClient.Disconnect(50)
	token := mqttClient.Publish(topic, byte(qos), false, body)
	if !token.WaitTimeout(time.Duration(client.TimeoutSeconds) * time.Second) {
		return TransportError("mqtt publish timeout")
	}
	if token.Error() != nil {
		return TransportError(fmt.Sprintf("mqtt publish failed: %v", token.Error()))
	}
	return nil
}

func (client *MqttTransportClient) Consume(
	agentID string,
	handler MQTTMessageHandler,
	service map[string]any,
	maxMessages int,
	pollTimeout time.Duration,
) (int, error) {
	brokerURL := mqttStringValue(service, "broker_url", client.BrokerURL)
	topic := mqttStringValue(service, "topic", "")
	if topic == "" {
		derived, err := MQTTTopicForAgent(agentID, client.TopicPrefix)
		if err != nil {
			return 0, err
		}
		topic = derived
	}
	qos := mqttNumberValue(service, "qos", client.QoS)
	if maxMessages <= 0 {
		maxMessages = int(^uint(0) >> 1)
	}
	if pollTimeout <= 0 {
		pollTimeout = time.Second
	}
	mqttClient, err := client.connect(brokerURL)
	if err != nil {
		return 0, err
	}
	defer mqttClient.Disconnect(50)
	processed := 0
	done := make(chan struct{}, 1)
	token := mqttClient.Subscribe(topic, byte(qos), func(_ mqtt.Client, message mqtt.Message) {
		if processed >= maxMessages {
			select {
			case done <- struct{}{}:
			default:
			}
			return
		}
		var parsed map[string]any
		if err := json.Unmarshal(message.Payload(), &parsed); err == nil && parsed != nil {
			_ = handler(parsed)
		}
		processed++
		if processed >= maxMessages {
			select {
			case done <- struct{}{}:
			default:
			}
		}
	})
	if !token.WaitTimeout(time.Duration(client.TimeoutSeconds) * time.Second) {
		return processed, TransportError("mqtt subscribe timeout")
	}
	if token.Error() != nil {
		return processed, TransportError(fmt.Sprintf("mqtt subscribe failed: %v", token.Error()))
	}
	select {
	case <-done:
	case <-time.After(pollTimeout):
	}
	return processed, nil
}
