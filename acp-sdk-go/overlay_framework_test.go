package acp

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func TestOverlayRuntimeExposesWellKnownHeadersAndRejectsNonObjectBody(t *testing.T) {
	tempDir := t.TempDir()
	agent, err := LoadOrCreate("agent:overlay.runtime@localhost:9541", &AcpAgentOptions{
		StorageDir:        filepath.Join(tempDir, "runtime-agent"),
		Endpoint:          "http://localhost:9541/acp/inbox",
		AllowInsecureHTTP: true,
		DiscoveryScheme:   "http",
	})
	if err != nil {
		t.Fatalf("runtime agent: %v", err)
	}
	runtime, err := NewOverlayFrameworkRuntime(agent, "http://localhost:9541", func(payload map[string]any) map[string]any {
		return map[string]any{
			"accepted": true,
			"echo":     payload,
		}
	}, nil)
	if err != nil {
		t.Fatalf("overlay runtime: %v", err)
	}
	headers := OverlayWellKnownHeaders()
	if headers["Cache-Control"] != "public, max-age=300" {
		t.Fatalf("unexpected cache-control header")
	}
	wellKnown, err := runtime.WellKnownDocument()
	if err != nil {
		t.Fatalf("well-known document should be built: %v", err)
	}
	if wellKnown["agent_id"] != "agent:overlay.runtime@localhost:9541" {
		t.Fatalf("unexpected well-known agent_id")
	}
	if wellKnown["version"] != "1.0" {
		t.Fatalf("unexpected well-known version")
	}
	invalidResponse := runtime.HandleMessageBody([]any{"invalid"})
	if invalidResponse.StatusCode != 400 {
		t.Fatalf("invalid request should return 400")
	}
	if invalidResponse.Body["state"] != "FAILED" {
		t.Fatalf("invalid request should be FAILED")
	}
	if invalidResponse.Body["reason_code"] != "POLICY_REJECTED" {
		t.Fatalf("invalid request reason code mismatch")
	}
}

func TestOverlayClientBootstrapsWellKnownAndSendsPayload(t *testing.T) {
	tempDir := t.TempDir()
	requestCounts := map[string]int{}
	var wellKnown map[string]any
	var identityPayload map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requestCounts[request.Method+" "+request.URL.Path]++
		switch {
		case request.Method == http.MethodGet && request.URL.Path == "/.well-known/acp":
			writer.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(writer).Encode(wellKnown)
		case request.Method == http.MethodGet && request.URL.Path == "/api/v1/acp/identity":
			writer.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(writer).Encode(identityPayload)
		case request.Method == http.MethodPost && request.URL.Path == "/acp/inbox":
			writer.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(writer).Encode(map[string]any{"status": "accepted"})
		default:
			http.NotFound(writer, request)
		}
	}))
	defer server.Close()

	receiver, err := LoadOrCreate("agent:overlay.receiver@localhost:9542", &AcpAgentOptions{
		StorageDir:        filepath.Join(tempDir, "receiver"),
		Endpoint:          server.URL + "/acp/inbox",
		AllowInsecureHTTP: true,
		DiscoveryScheme:   "http",
	})
	if err != nil {
		t.Fatalf("receiver agent: %v", err)
	}
	wellKnown, err = receiver.BuildWellKnownDocument(server.URL, "")
	if err != nil {
		t.Fatalf("receiver well-known: %v", err)
	}
	identityPayload = map[string]any{
		"identity_document": receiver.IdentityDocument,
	}

	sender, err := LoadOrCreate("agent:overlay.sender@localhost:9543", &AcpAgentOptions{
		StorageDir:        filepath.Join(tempDir, "sender"),
		AllowInsecureHTTP: true,
		DiscoveryScheme:   "http",
	})
	if err != nil {
		t.Fatalf("sender agent: %v", err)
	}
	client := NewOverlayClient(sender)
	response, err := client.SendACP(
		server.URL,
		map[string]any{"kind": "overlay-go-test"},
		"",
		"overlay:go:outbound",
		DeliveryAuto,
		120,
	)
	if err != nil {
		t.Fatalf("overlay outbound send: %v", err)
	}

	target, ok := response["target"].(*OverlayTarget)
	if !ok || target == nil {
		t.Fatalf("target should be present")
	}
	if target.AgentID != "agent:overlay.receiver@localhost:9542" {
		t.Fatalf("target agent mismatch")
	}
	if target.WellKnownURL != server.URL+"/.well-known/acp" {
		t.Fatalf("well-known URL mismatch")
	}
	sendResult, ok := response["send_result"].(SendResult)
	if !ok {
		t.Fatalf("send_result should be present")
	}
	if len(sendResult.Outcomes) != 1 {
		t.Fatalf("expected one delivery outcome")
	}
	state := sendResult.Outcomes[0].State
	if state != StateDelivered && state != StateAcknowledged {
		t.Fatalf("unexpected delivery state: %s", state)
	}
	if requestCounts["GET /.well-known/acp"] == 0 {
		t.Fatalf("well-known endpoint should be called")
	}
	if requestCounts["GET /api/v1/acp/identity"] == 0 {
		t.Fatalf("identity endpoint should be called")
	}
	if requestCounts["POST /acp/inbox"] == 0 {
		t.Fatalf("inbox endpoint should be called")
	}
}
