package acp

import "testing"

func TestAuthConfigFromAnyParsesUsernamePassword(t *testing.T) {
	auth, err := AuthConfigFromAny(map[string]any{
		"type": "username_password",
		"parameters": map[string]any{
			"username": "agentA",
			"password": "secret",
		},
	})
	if err != nil {
		t.Fatalf("auth parsing should succeed: %v", err)
	}
	if auth == nil || auth.Type != "username_password" {
		t.Fatalf("auth type should be username_password")
	}
	if auth.Parameters["username"] != "agentA" {
		t.Fatalf("username should be preserved")
	}
}

func TestBuildHintsWithAuthIncludeAuthObject(t *testing.T) {
	auth := &AuthConfig{
		Type: "username_password",
		Parameters: map[string]string{
			"username": "agentA",
			"password": "secret",
		},
	}
	amqpHint, err := BuildAMQPServiceHintWithAuth("agent:sender@demo", "amqps://broker.local", "acp.exchange", auth)
	if err != nil {
		t.Fatalf("amqp hint should be built: %v", err)
	}
	if _, ok := amqpHint["auth"].(map[string]any); !ok {
		t.Fatalf("amqp hint should include auth object")
	}

	mqttHint, err := BuildMQTTServiceHintWithAuth("agent:sender@demo", "mqtts://broker.local:8883", "", 1, "acp/agent", auth)
	if err != nil {
		t.Fatalf("mqtt hint should be built: %v", err)
	}
	if _, ok := mqttHint["auth"].(map[string]any); !ok {
		t.Fatalf("mqtt hint should include auth object")
	}
}
