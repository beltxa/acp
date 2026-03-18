package main

import (
	"fmt"
	"log"
	"os"
	"strings"

	acp "github.com/beltxa/acp/sdks/go"
)

func main() {
	targetBaseURL := os.Getenv("ACP_TARGET_BASE_URL")
	if targetBaseURL == "" {
		targetBaseURL = "http://localhost:9010"
	}
	agentID := os.Getenv("ACP_FROM_AGENT_ID")
	if agentID == "" {
		agentID = "agent:overlay.go.sender@localhost:9041"
	}
	allowInsecureHTTP := strings.EqualFold(os.Getenv("ACP_ALLOW_INSECURE_HTTP"), "true")
	agent, err := acp.LoadOrCreate(agentID, &acp.AcpAgentOptions{
		StorageDir:          ".acp-go-data",
		AllowInsecureHTTP:   allowInsecureHTTP,
		DiscoveryScheme:     "http",
		DefaultDeliveryMode: acp.DeliveryAuto,
	})
	if err != nil {
		log.Fatal(err)
	}
	client := acp.NewOverlayClient(agent)
	response, err := client.SendACP(
		targetBaseURL,
		map[string]any{
			"kind": "overlay-go-demo",
			"from": agentID,
		},
		"",
		"overlay:go:demo",
		acp.DeliveryAuto,
		120,
	)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("%#v\n", response)
}
