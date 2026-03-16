package acp

import (
	"encoding/json"
	"os"
	"testing"
)

func loadJSONFixtureMap(t *testing.T, path string) map[string]any {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("unable to read fixture %s: %v", path, err)
	}
	var parsed map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		t.Fatalf("unable to parse fixture %s: %v", path, err)
	}
	return parsed
}

func asMapFromFixture(t *testing.T, value any, message string) map[string]any {
	t.Helper()
	parsed, ok := value.(map[string]any)
	if !ok {
		t.Fatal(message)
	}
	return parsed
}

func asArrayFromFixture(t *testing.T, value any, message string) []any {
	t.Helper()
	parsed, ok := value.([]any)
	if !ok {
		t.Fatal(message)
	}
	return parsed
}

func asFloat64FromFixture(t *testing.T, value any, message string) float64 {
	t.Helper()
	parsed, ok := value.(float64)
	if !ok {
		t.Fatal(message)
	}
	return parsed
}

func jsonEqual(left any, right any) bool {
	leftBytes, leftErr := json.Marshal(left)
	rightBytes, rightErr := json.Marshal(right)
	if leftErr != nil || rightErr != nil {
		return false
	}
	return string(leftBytes) == string(rightBytes)
}
