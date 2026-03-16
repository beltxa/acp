package acp

import (
	"os"
	"path/filepath"
	"testing"
)

func amqpVectorsDir(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "tests", "vectors", "amqp")
}

func TestRequiredAMQPFixtureFilesExist(t *testing.T) {
	required := []string{
		"python_to_python_send.json",
		"java_to_python_send.json",
		"python_to_java_send.json",
		"multi_recipient_send_B.json",
		"multi_recipient_send_C.json",
		"multi_recipient_send_D.json",
		"duplicate_delivery_case.json",
		"relay_amqp_fallback_case.json",
		"ack_example.json",
		"fail_example.json",
	}
	for _, fixture := range required {
		if _, err := os.Stat(filepath.Join(amqpVectorsDir(t), fixture)); err != nil {
			t.Fatalf("missing required fixture: %s", fixture)
		}
	}
}

func TestAMQPStandardFixturesMatchRoutingAndHeaderConventions(t *testing.T) {
	standard := []string{
		"python_to_python_send.json",
		"java_to_python_send.json",
		"python_to_java_send.json",
		"multi_recipient_send_B.json",
		"multi_recipient_send_C.json",
		"multi_recipient_send_D.json",
		"ack_example.json",
		"fail_example.json",
	}
	for _, fixture := range standard {
		fixtureMap := loadJSONFixtureMap(t, filepath.Join(amqpVectorsDir(t), fixture))
		body := asMapFromFixture(t, fixtureMap["serialized_body"], "serialized_body must be an object")
		if _, err := ParseAcpMessage(body); err != nil {
			t.Fatalf("fixture %s serialized_body must parse as ACP message: %v", fixture, err)
		}
		envelope := asMapFromFixture(t, body["envelope"], "envelope must be an object")
		recipients := asArrayFromFixture(t, envelope["recipients"], "recipients must be an array")
		if len(recipients) != 1 {
			t.Fatalf("fixture %s must be single-recipient", fixture)
		}
		recipient, ok := recipients[0].(string)
		if !ok {
			t.Fatalf("fixture %s recipient must be string", fixture)
		}
		transport := asMapFromFixture(t, fixtureMap["transport_metadata"], "transport_metadata must be an object")
		headers := asMapFromFixture(t, transport["headers"], "headers must be an object")
		expectedHeaders := map[string]any{}
		for key, value := range AMQPMetadataHeaders(body) {
			expectedHeaders[key] = value
		}
		if !jsonEqual(headers, expectedHeaders) {
			t.Fatalf("fixture %s headers mismatch", fixture)
		}
		expectedRoutingKey, err := AMQPRoutingKeyForAgent(recipient)
		if err != nil {
			t.Fatalf("fixture %s routing key derivation failed: %v", fixture, err)
		}
		if transport["routing_key"] != expectedRoutingKey {
			t.Fatalf("fixture %s routing key mismatch", fixture)
		}
		expectedQueue, err := AMQPQueueNameForAgent(recipient)
		if err != nil {
			t.Fatalf("fixture %s queue derivation failed: %v", fixture, err)
		}
		if transport["queue"] != expectedQueue {
			t.Fatalf("fixture %s queue mismatch", fixture)
		}
	}
}

func TestAMQPDuplicateFixtureUsesSameMessageID(t *testing.T) {
	fixture := loadJSONFixtureMap(t, filepath.Join(amqpVectorsDir(t), "duplicate_delivery_case.json"))
	original := asMapFromFixture(t, fixture["original_message"], "original_message must be object")
	duplicate := asMapFromFixture(t, fixture["duplicate_message"], "duplicate_message must be object")
	originalBody := asMapFromFixture(t, original["serialized_body"], "original serialized_body must be object")
	duplicateBody := asMapFromFixture(t, duplicate["serialized_body"], "duplicate serialized_body must be object")
	if _, err := ParseAcpMessage(originalBody); err != nil {
		t.Fatalf("original message should parse: %v", err)
	}
	if _, err := ParseAcpMessage(duplicateBody); err != nil {
		t.Fatalf("duplicate message should parse: %v", err)
	}
	originalEnvelope := asMapFromFixture(t, originalBody["envelope"], "original envelope must be object")
	duplicateEnvelope := asMapFromFixture(t, duplicateBody["envelope"], "duplicate envelope must be object")
	if originalEnvelope["message_id"] != duplicateEnvelope["message_id"] {
		t.Fatalf("duplicate fixture should preserve message_id")
	}
}

func TestAMQPRelayFallbackFixturePreservesSerializedBody(t *testing.T) {
	fixture := loadJSONFixtureMap(t, filepath.Join(amqpVectorsDir(t), "relay_amqp_fallback_case.json"))
	input := asMapFromFixture(t, fixture["input_acp_message"], "input_acp_message must be object")
	emitted := asMapFromFixture(t, fixture["emitted_amqp_message"], "emitted_amqp_message must be object")
	inputBody := asMapFromFixture(t, input["serialized_body"], "input serialized_body must be object")
	emittedBody := asMapFromFixture(t, emitted["serialized_body"], "emitted serialized_body must be object")
	if _, err := ParseAcpMessage(inputBody); err != nil {
		t.Fatalf("input message should parse: %v", err)
	}
	if _, err := ParseAcpMessage(emittedBody); err != nil {
		t.Fatalf("emitted message should parse: %v", err)
	}
	if !jsonEqual(inputBody, emittedBody) {
		t.Fatalf("relay fallback fixture should preserve serialized body")
	}
}
