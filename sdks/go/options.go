/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"math"
	"strconv"
	"strings"
)

type AcpAgentOptions struct {
	StorageDir               string
	Endpoint                 string
	RelayURL                 string
	RelayHints               []string
	EnterpriseDirectoryHints []string
	DiscoveryScheme          string
	TrustProfile             string
	DefaultDeliveryMode      DeliveryMode
	HTTPTimeoutSeconds       int
	AllowInsecureHTTP        bool
	AllowInsecureTLS         bool
	MTLSEnabled              bool
	CAFile                   string
	CertFile                 string
	KeyFile                  string
	DirectTransportAuth      map[string]any
	RelayTransportAuth       map[string]any
	KeyProvider              string
	VaultURL                 string
	VaultPath                string
	VaultTokenEnv            string
	VaultToken               string
	AMQPBrokerURL            string
	AMQPExchange             string
	AMQPExchangeType         string
	AMQPAuth                 map[string]any
	MQTTBrokerURL            string
	MQTTQoS                  int
	MQTTTopicPrefix          string
	MQTTAuth                 map[string]any
	Extra                    map[string]any
}

func DefaultAgentOptions() AcpAgentOptions {
	return AcpAgentOptions{
		StorageDir:               ".acp-data",
		RelayURL:                 "https://localhost:8080",
		RelayHints:               []string{},
		EnterpriseDirectoryHints: []string{},
		DiscoveryScheme:          "https",
		TrustProfile:             "self_asserted",
		DefaultDeliveryMode:      DeliveryAuto,
		HTTPTimeoutSeconds:       10,
		AllowInsecureHTTP:        false,
		AllowInsecureTLS:         false,
		MTLSEnabled:              false,
		DirectTransportAuth:      nil,
		RelayTransportAuth:       nil,
		KeyProvider:              "local",
		VaultTokenEnv:            "VAULT_TOKEN",
		AMQPExchange:             DefaultAMQPExchange,
		AMQPExchangeType:         DefaultAMQPExchangeType,
		AMQPAuth:                 nil,
		MQTTQoS:                  1,
		MQTTTopicPrefix:          DefaultMQTTTopicPrefix,
		MQTTAuth:                 nil,
		Extra:                    map[string]any{},
	}
}

func OptionsFromConfigMap(config map[string]any) AcpAgentOptions {
	options := DefaultAgentOptions()
	if config == nil {
		return options
	}
	options.AllowInsecureHTTP = asBool(config["allow_insecure_http"], false)
	options.AllowInsecureTLS = asBool(config["allow_insecure_tls"], false)
	options.MTLSEnabled = asBool(config["mtls_enabled"], false)
	options.CAFile = asString(config["ca_file"])
	options.CertFile = asString(config["cert_file"])
	options.KeyFile = asString(config["key_file"])
	options.DirectTransportAuth = asMapOption(config["direct_transport_auth"])
	options.RelayTransportAuth = asMapOption(config["relay_transport_auth"])
	options.KeyProvider = firstNonBlankString(asString(config["key_provider"]), "local")
	options.VaultURL = asString(config["vault_url"])
	options.VaultPath = asString(config["vault_path"])
	options.VaultTokenEnv = firstNonBlankString(asString(config["vault_token_env"]), "VAULT_TOKEN")
	options.VaultToken = asString(config["vault_token"])
	options.Endpoint = asString(config["endpoint"])
	options.RelayURL = firstNonBlankString(asString(config["relay_url"]), options.RelayURL)
	options.DiscoveryScheme = firstNonBlankString(asString(config["discovery_scheme"]), options.DiscoveryScheme)
	options.StorageDir = firstNonBlankString(asString(config["storage_dir"]), options.StorageDir)
	options.AMQPBrokerURL = asString(config["amqp_broker_url"])
	options.AMQPExchange = firstNonBlankString(asString(config["amqp_exchange"]), options.AMQPExchange)
	options.AMQPExchangeType = firstNonBlankString(asString(config["amqp_exchange_type"]), options.AMQPExchangeType)
	options.AMQPAuth = asMapOption(config["amqp_auth"])
	options.MQTTBrokerURL = asString(config["mqtt_broker_url"])
	options.MQTTTopicPrefix = firstNonBlankString(asString(config["mqtt_topic_prefix"]), options.MQTTTopicPrefix)
	options.MQTTQoS = clampInt(asNumber(config["mqtt_qos"], float64(options.MQTTQoS)), 0, 2)
	options.MQTTAuth = asMapOption(config["mqtt_auth"])
	options.RelayHints = asStringList(config["relay_hints"])
	options.EnterpriseDirectoryHints = asStringList(config["enterprise_directory_hints"])
	return options
}

func (options AcpAgentOptions) ToConfigMap() map[string]any {
	return map[string]any{
		"allow_insecure_http": options.AllowInsecureHTTP,
		"allow_insecure_tls":  options.AllowInsecureTLS,
		"mtls_enabled":        options.MTLSEnabled,
		"ca_file":             nullableString(options.CAFile),
		"cert_file":           nullableString(options.CertFile),
		"key_file":            nullableString(options.KeyFile),
		"direct_transport_auth": nullableMap(options.DirectTransportAuth),
		"relay_transport_auth":  nullableMap(options.RelayTransportAuth),
		"key_provider":        options.KeyProvider,
		"vault_url":           nullableString(options.VaultURL),
		"vault_path":          nullableString(options.VaultPath),
		"vault_token_env":     firstNonBlankString(options.VaultTokenEnv, "VAULT_TOKEN"),
		"amqp_auth":           nullableMap(options.AMQPAuth),
		"mqtt_auth":           nullableMap(options.MQTTAuth),
	}
}

func asBool(value any, fallback bool) bool {
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		switch strings.ToLower(strings.TrimSpace(typed)) {
		case "1", "true", "yes", "on":
			return true
		case "0", "false", "no", "off":
			return false
		default:
			return fallback
		}
	default:
		return fallback
	}
}

func asString(value any) string {
	raw, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(raw)
}

func asNumber(value any, fallback float64) float64 {
	switch typed := value.(type) {
	case float64:
		if math.IsNaN(typed) || math.IsInf(typed, 0) {
			return fallback
		}
		return typed
	case float32:
		if math.IsNaN(float64(typed)) || math.IsInf(float64(typed), 0) {
			return fallback
		}
		return float64(typed)
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case string:
		if typed == "" {
			return fallback
		}
		parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		if err == nil && !math.IsNaN(parsed) && !math.IsInf(parsed, 0) {
			return parsed
		}
		return fallback
	default:
		return fallback
	}
}

func asStringList(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return []string{}
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		normalized := asString(item)
		if normalized != "" {
			out = append(out, normalized)
		}
	}
	return out
}

func nullableString(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return strings.TrimSpace(value)
}

func nullableMap(value map[string]any) any {
	if len(value) == 0 {
		return nil
	}
	return value
}

func asMapOption(value any) map[string]any {
	parsed, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	return parsed
}

func clampInt(value float64, min, max int) int {
	asInt := int(value)
	if asInt < min {
		return min
	}
	if asInt > max {
		return max
	}
	return asInt
}
