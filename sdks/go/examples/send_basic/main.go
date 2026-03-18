package main

import (
	"log"

	acp "github.com/beltxa/acp/sdks/go"
)

func main() {
	agent, err := acp.LoadOrCreate("agent:demo", nil)
	if err != nil {
		log.Fatal(err)
	}

	_, err = agent.SendBasic(
		[]string{"agent:other"},
		map[string]any{"message": "hello"},
		"ping",
	)
	if err != nil {
		log.Fatal(err)
	}
}
