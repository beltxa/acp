package acp

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func wellKnownVectorsDir(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "tests", "vectors", "well_known")
}

func TestWellKnownValidFixtureParses(t *testing.T) {
	value := loadJSONFixtureMap(t, filepath.Join(wellKnownVectorsDir(t), "valid_basic.json"))
	parsed, err := ParseWellKnownDocument(value)
	if err != nil {
		t.Fatalf("valid fixture should parse: %v", err)
	}
	if parsed["agent_id"] != "agent:shipping.bot@company.local" {
		t.Fatalf("agent_id mismatch in valid fixture")
	}
}

func TestWellKnownInvalidFixturesFailValidation(t *testing.T) {
	invalidFixtures := []string{
		"invalid_missing_agent_id.json",
		"invalid_missing_version.json",
		"invalid_identity_document_type.json",
		"invalid_identity_document_relative_path.json",
		"invalid_identity_document_url.json",
		"invalid_transports_type.json",
		"invalid_transport_hint_shape.json",
		"invalid_transport_endpoint_type.json",
		"invalid_transport_endpoint_url.json",
		"invalid_version.json",
		"invalid_security_profile.json",
	}
	for _, fixture := range invalidFixtures {
		value := loadJSONFixtureMap(t, filepath.Join(wellKnownVectorsDir(t), fixture))
		if _, err := ParseWellKnownDocument(value); err == nil {
			t.Fatalf("fixture %s must fail validation", fixture)
		}
	}
}

func TestWellKnownMalformedFixtureFailsParse(t *testing.T) {
	path := filepath.Join(wellKnownVectorsDir(t), "malformed_json.txt")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("unable to read fixture %s: %v", path, err)
	}
	var parsed any
	if err := json.Unmarshal(raw, &parsed); err == nil {
		t.Fatalf("malformed fixture must be invalid JSON")
	}
}
