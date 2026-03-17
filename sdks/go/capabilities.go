/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"strings"
)

type CapabilityMatch struct {
	Compatible bool
	Reason     string
}

type AgentCapabilities struct {
	AgentID          string          `json:"agent_id"`
	ProtocolVersions []string        `json:"protocol_versions"`
	CryptoSuites     []string        `json:"crypto_suites"`
	Transports       []string        `json:"transports"`
	Supports         map[string]bool `json:"supports"`
}

func NewAgentCapabilities(agentID string) AgentCapabilities {
	return AgentCapabilities{
		AgentID:          agentID,
		ProtocolVersions: []string{ACPVersion},
		CryptoSuites:     []string{DefaultCryptoSuite},
		Transports:       []string{"https", "http", "relay", "amqp", "mqtt"},
		Supports: map[string]bool{
			"capabilities": true,
			"compensate":   true,
			"amqp":         true,
			"mqtt":         true,
			"overlay":      true,
		},
	}
}

func (capabilities AgentCapabilities) ToMap() map[string]any {
	out := map[string]any{
		"agent_id":          capabilities.AgentID,
		"protocol_versions": append([]string{}, capabilities.ProtocolVersions...),
		"crypto_suites":     append([]string{}, capabilities.CryptoSuites...),
		"transports":        append([]string{}, capabilities.Transports...),
		"supports":          map[string]bool{},
	}
	supports := out["supports"].(map[string]bool)
	for key, value := range capabilities.Supports {
		supports[key] = value
	}
	return out
}

func AgentCapabilitiesFromMap(value map[string]any, fallbackAgentID string) AgentCapabilities {
	capabilities := NewAgentCapabilities(fallbackAgentID)
	if value == nil {
		return capabilities
	}
	if agentID, ok := value["agent_id"].(string); ok && strings.TrimSpace(agentID) != "" {
		capabilities.AgentID = strings.TrimSpace(agentID)
	}
	capabilities.ProtocolVersions = asStringSlice(value["protocol_versions"], capabilities.ProtocolVersions, false)
	capabilities.CryptoSuites = asStringSlice(value["crypto_suites"], capabilities.CryptoSuites, false)
	capabilities.Transports = asStringSlice(value["transports"], capabilities.Transports, true)
	if supportsRaw, ok := value["supports"].(map[string]any); ok {
		supports := map[string]bool{}
		for key, raw := range supportsRaw {
			supports[key] = asBool(raw, false)
		}
		capabilities.Supports = supports
	}
	return capabilities
}

func (capabilities AgentCapabilities) ChooseCompatible(remote AgentCapabilities) CapabilityMatch {
	if !intersects(capabilities.ProtocolVersions, remote.ProtocolVersions) {
		return CapabilityMatch{Compatible: false, Reason: "No compatible protocol version"}
	}
	if !intersects(capabilities.CryptoSuites, remote.CryptoSuites) {
		return CapabilityMatch{Compatible: false, Reason: "No compatible crypto suite"}
	}
	if !intersects(capabilities.Transports, remote.Transports) {
		return CapabilityMatch{Compatible: false, Reason: "No compatible transport"}
	}
	return CapabilityMatch{Compatible: true}
}

func intersects(left []string, right []string) bool {
	rightSet := map[string]struct{}{}
	for _, item := range right {
		rightSet[item] = struct{}{}
	}
	for _, item := range left {
		if _, ok := rightSet[item]; ok {
			return true
		}
	}
	return false
}

func asStringSlice(value any, fallback []string, lower bool) []string {
	items, ok := value.([]any)
	if !ok {
		return fallback
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		raw, ok := item.(string)
		if !ok {
			continue
		}
		normalized := strings.TrimSpace(raw)
		if normalized == "" {
			continue
		}
		if lower {
			normalized = strings.ToLower(normalized)
		}
		out = append(out, normalized)
	}
	if len(out) == 0 {
		return fallback
	}
	return out
}
