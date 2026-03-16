package acp

import (
	"os"
	"path/filepath"
	"testing"
)

func mqttVectorsDir(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "tests", "vectors", "mqtt")
}

func TestRequiredMQTTFixtureFilesExist(t *testing.T) {
	required := []string{
		"python_to_python_send.json",
		"java_to_python_send.json",
		"python_to_java_send.json",
		"multi_recipient_send_B.json",
		"multi_recipient_send_C.json",
		"multi_recipient_send_D.json",
		"duplicate_delivery_case.json",
		"ack_example.json",
		"fail_example.json",
	}
	for _, fixture := range required {
		if _, err := os.Stat(filepath.Join(mqttVectorsDir(t), fixture)); err != nil {
			t.Fatalf("missing required fixture: %s", fixture)
		}
	}
}

func TestMQTTStandardFixturesMatchTopicAndMetadataConventions(t *testing.T) {
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
		fixtureMap := loadJSONFixtureMap(t, filepath.Join(mqttVectorsDir(t), fixture))
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
		expectedTopic, err := MQTTTopicForAgent(recipient, "")
		if err != nil {
			t.Fatalf("fixture %s topic derivation failed: %v", fixture, err)
		}
		if transport["topic"] != expectedTopic {
			t.Fatalf("fixture %s topic mismatch", fixture)
		}
		if int(asFloat64FromFixture(t, transport["qos"], "qos must be number")) != 1 {
			t.Fatalf("fixture %s qos mismatch", fixture)
		}
		userProperties := asMapFromFixture(t, transport["user_properties"], "user_properties must be object")
		expectedProperties := map[string]any{}
		for key, value := range MQTTMetadataProperties(body) {
			expectedProperties[key] = value
		}
		if !jsonEqual(userProperties, expectedProperties) {
			t.Fatalf("fixture %s user properties mismatch", fixture)
		}
	}
}

func TestMQTTDuplicateFixtureUsesSameMessageID(t *testing.T) {
	fixture := loadJSONFixtureMap(t, filepath.Join(mqttVectorsDir(t), "duplicate_delivery_case.json"))
	original := asMapFromFixture(t, fixture["original_message"], "original_message must be object")
	duplicate := asMapFromFixture(t, fixture["duplicate_message"], "duplicate_message must be object")
	originalBody := asMapFromFixture(t, original["serialized_body"], "original serialized_body must be object")
	duplicateBody := asMapFromFixture(t, duplicate["serialized_body"], "duplicate serialized_body must be object")
	originalEnvelope := asMapFromFixture(t, originalBody["envelope"], "original envelope must be object")
	duplicateEnvelope := asMapFromFixture(t, duplicateBody["envelope"], "duplicate envelope must be object")
	if originalEnvelope["message_id"] != duplicateEnvelope["message_id"] {
		t.Fatalf("duplicate fixture should preserve message_id")
	}
}
