/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AcpAgentOptions {
    private Path storageDir = Paths.get(".acp-data");
    private String endpoint;
    private String relayUrl = "https://localhost:8080";
    private List<String> relayHints = new ArrayList<>();
    private List<String> enterpriseDirectoryHints = new ArrayList<>();
    private String discoveryScheme = "https";
    private String trustProfile = "self_asserted";
    private AgentCapabilities capabilities;
    private DeliveryMode defaultDeliveryMode = DeliveryMode.AUTO;
    private int httpTimeoutSeconds = 10;
    private boolean allowInsecureHttp = false;
    private boolean allowInsecureTls = false;
    private boolean mtlsEnabled = false;
    private String caFile;
    private String certFile;
    private String keyFile;
    private String keyProvider = "local";
    private String vaultUrl;
    private String vaultPath;
    private String vaultTokenEnv = "VAULT_TOKEN";
    private String vaultToken;
    private KeyProvider keyProviderInstance;
    private String amqpBrokerUrl;
    private String amqpExchange = AmqpTransportClient.DEFAULT_EXCHANGE;
    private String amqpExchangeType = AmqpTransportClient.DEFAULT_EXCHANGE_TYPE;
    private AmqpTransportClient amqpTransport;
    private String mqttBrokerUrl;
    private int mqttQos = MqttTransportClient.DEFAULT_QOS;
    private String mqttTopicPrefix = MqttTransportClient.DEFAULT_TOPIC_PREFIX;
    private MqttTransportClient mqttTransport;

    public Path getStorageDir() {
        return storageDir;
    }

    public AcpAgentOptions setStorageDir(Path storageDir) {
        this.storageDir = storageDir;
        return this;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public AcpAgentOptions setEndpoint(String endpoint) {
        this.endpoint = endpoint;
        return this;
    }

    public String getRelayUrl() {
        return relayUrl;
    }

    public AcpAgentOptions setRelayUrl(String relayUrl) {
        this.relayUrl = relayUrl;
        return this;
    }

    public List<String> getRelayHints() {
        return relayHints;
    }

    public AcpAgentOptions setRelayHints(List<String> relayHints) {
        this.relayHints = relayHints == null ? new ArrayList<>() : new ArrayList<>(relayHints);
        return this;
    }

    public List<String> getEnterpriseDirectoryHints() {
        return enterpriseDirectoryHints;
    }

    public AcpAgentOptions setEnterpriseDirectoryHints(List<String> enterpriseDirectoryHints) {
        this.enterpriseDirectoryHints = enterpriseDirectoryHints == null ? new ArrayList<>() : new ArrayList<>(enterpriseDirectoryHints);
        return this;
    }

    public String getDiscoveryScheme() {
        return discoveryScheme;
    }

    public AcpAgentOptions setDiscoveryScheme(String discoveryScheme) {
        this.discoveryScheme = discoveryScheme;
        return this;
    }

    public String getTrustProfile() {
        return trustProfile;
    }

    public AcpAgentOptions setTrustProfile(String trustProfile) {
        this.trustProfile = trustProfile;
        return this;
    }

    public AgentCapabilities getCapabilities() {
        return capabilities;
    }

    public AcpAgentOptions setCapabilities(AgentCapabilities capabilities) {
        this.capabilities = capabilities;
        return this;
    }

    public DeliveryMode getDefaultDeliveryMode() {
        return defaultDeliveryMode;
    }

    public AcpAgentOptions setDefaultDeliveryMode(DeliveryMode defaultDeliveryMode) {
        this.defaultDeliveryMode = defaultDeliveryMode;
        return this;
    }

    public int getHttpTimeoutSeconds() {
        return httpTimeoutSeconds;
    }

    public AcpAgentOptions setHttpTimeoutSeconds(int httpTimeoutSeconds) {
        this.httpTimeoutSeconds = httpTimeoutSeconds;
        return this;
    }

    public boolean isAllowInsecureHttp() {
        return allowInsecureHttp;
    }

    public AcpAgentOptions setAllowInsecureHttp(boolean allowInsecureHttp) {
        this.allowInsecureHttp = allowInsecureHttp;
        return this;
    }

    public boolean isAllowInsecureTls() {
        return allowInsecureTls;
    }

    public AcpAgentOptions setAllowInsecureTls(boolean allowInsecureTls) {
        this.allowInsecureTls = allowInsecureTls;
        return this;
    }

    public String getCaFile() {
        return caFile;
    }

    public AcpAgentOptions setCaFile(String caFile) {
        this.caFile = caFile;
        return this;
    }

    public boolean isMtlsEnabled() {
        return mtlsEnabled;
    }

    public AcpAgentOptions setMtlsEnabled(boolean mtlsEnabled) {
        this.mtlsEnabled = mtlsEnabled;
        return this;
    }

    public String getCertFile() {
        return certFile;
    }

    public AcpAgentOptions setCertFile(String certFile) {
        this.certFile = certFile;
        return this;
    }

    public String getKeyFile() {
        return keyFile;
    }

    public AcpAgentOptions setKeyFile(String keyFile) {
        this.keyFile = keyFile;
        return this;
    }

    public String getAmqpBrokerUrl() {
        return amqpBrokerUrl;
    }

    public AcpAgentOptions setAmqpBrokerUrl(String amqpBrokerUrl) {
        this.amqpBrokerUrl = amqpBrokerUrl;
        return this;
    }

    public String getAmqpExchange() {
        return amqpExchange;
    }

    public AcpAgentOptions setAmqpExchange(String amqpExchange) {
        this.amqpExchange = amqpExchange;
        return this;
    }

    public String getAmqpExchangeType() {
        return amqpExchangeType;
    }

    public AcpAgentOptions setAmqpExchangeType(String amqpExchangeType) {
        this.amqpExchangeType = amqpExchangeType;
        return this;
    }

    public AmqpTransportClient getAmqpTransport() {
        return amqpTransport;
    }

    public AcpAgentOptions setAmqpTransport(AmqpTransportClient amqpTransport) {
        this.amqpTransport = amqpTransport;
        return this;
    }

    public String getMqttBrokerUrl() {
        return mqttBrokerUrl;
    }

    public AcpAgentOptions setMqttBrokerUrl(String mqttBrokerUrl) {
        this.mqttBrokerUrl = mqttBrokerUrl;
        return this;
    }

    public int getMqttQos() {
        return mqttQos;
    }

    public AcpAgentOptions setMqttQos(int mqttQos) {
        this.mqttQos = mqttQos;
        return this;
    }

    public String getMqttTopicPrefix() {
        return mqttTopicPrefix;
    }

    public AcpAgentOptions setMqttTopicPrefix(String mqttTopicPrefix) {
        this.mqttTopicPrefix = mqttTopicPrefix;
        return this;
    }

    public MqttTransportClient getMqttTransport() {
        return mqttTransport;
    }

    public AcpAgentOptions setMqttTransport(MqttTransportClient mqttTransport) {
        this.mqttTransport = mqttTransport;
        return this;
    }

    public String getKeyProvider() {
        return keyProvider;
    }

    public AcpAgentOptions setKeyProvider(String keyProvider) {
        if (keyProvider == null || keyProvider.isBlank()) {
            this.keyProvider = "local";
        } else {
            this.keyProvider = keyProvider.trim().toLowerCase();
        }
        return this;
    }

    public String getVaultUrl() {
        return vaultUrl;
    }

    public AcpAgentOptions setVaultUrl(String vaultUrl) {
        this.vaultUrl = vaultUrl;
        return this;
    }

    public String getVaultPath() {
        return vaultPath;
    }

    public AcpAgentOptions setVaultPath(String vaultPath) {
        this.vaultPath = vaultPath;
        return this;
    }

    public String getVaultTokenEnv() {
        return vaultTokenEnv;
    }

    public AcpAgentOptions setVaultTokenEnv(String vaultTokenEnv) {
        if (vaultTokenEnv == null || vaultTokenEnv.isBlank()) {
            this.vaultTokenEnv = "VAULT_TOKEN";
        } else {
            this.vaultTokenEnv = vaultTokenEnv.trim();
        }
        return this;
    }

    public String getVaultToken() {
        return vaultToken;
    }

    public AcpAgentOptions setVaultToken(String vaultToken) {
        this.vaultToken = vaultToken;
        return this;
    }

    public KeyProvider getKeyProviderInstance() {
        return keyProviderInstance;
    }

    public AcpAgentOptions setKeyProviderInstance(KeyProvider keyProviderInstance) {
        this.keyProviderInstance = keyProviderInstance;
        return this;
    }

    public Map<String, Object> toConfigMap() {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("allow_insecure_http", allowInsecureHttp);
        values.put("allow_insecure_tls", allowInsecureTls);
        values.put("mtls_enabled", mtlsEnabled);
        values.put("ca_file", caFile);
        values.put("cert_file", certFile);
        values.put("key_file", keyFile);
        values.put("key_provider", keyProvider);
        values.put("vault_url", vaultUrl);
        values.put("vault_path", vaultPath);
        values.put("vault_token_env", vaultTokenEnv);
        return values;
    }

    public static AcpAgentOptions fromConfigMap(Map<String, Object> config) {
        AcpAgentOptions options = new AcpAgentOptions();
        if (config == null) {
            return options;
        }
        options.setAllowInsecureHttp(asBool(config.get("allow_insecure_http"), false));
        options.setAllowInsecureTls(asBool(config.get("allow_insecure_tls"), false));
        options.setMtlsEnabled(asBool(config.get("mtls_enabled"), false));
        options.setCaFile(asString(config.get("ca_file")));
        options.setCertFile(asString(config.get("cert_file")));
        options.setKeyFile(asString(config.get("key_file")));
        options.setKeyProvider(asString(config.get("key_provider")));
        options.setVaultUrl(asString(config.get("vault_url")));
        options.setVaultPath(asString(config.get("vault_path")));
        options.setVaultTokenEnv(asString(config.get("vault_token_env")));
        return options;
    }

    private static boolean asBool(Object value, boolean defaultValue) {
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof Boolean bool) {
            return bool;
        }
        if (value instanceof String str) {
            String normalized = str.trim().toLowerCase();
            if (normalized.isEmpty()) {
                return defaultValue;
            }
            if (normalized.equals("1") || normalized.equals("true") || normalized.equals("yes") || normalized.equals("on")) {
                return true;
            }
            if (normalized.equals("0") || normalized.equals("false") || normalized.equals("no") || normalized.equals("off")) {
                return false;
            }
        }
        return defaultValue;
    }

    private static String asString(Object value) {
        if (!(value instanceof String str)) {
            return null;
        }
        String normalized = str.trim();
        return normalized.isEmpty() ? null : normalized;
    }
}
