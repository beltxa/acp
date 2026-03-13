package org.acp.client;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class AcpAgentOptions {
    private Path storageDir = Paths.get(".acp-data");
    private String endpoint;
    private String relayUrl = "http://localhost:8080";
    private List<String> relayHints = new ArrayList<>();
    private List<String> enterpriseDirectoryHints = new ArrayList<>();
    private String discoveryScheme = "https";
    private String trustProfile = "self_asserted";
    private AgentCapabilities capabilities;
    private DeliveryMode defaultDeliveryMode = DeliveryMode.AUTO;
    private int httpTimeoutSeconds = 10;
    private String amqpBrokerUrl;
    private String amqpExchange = AmqpTransportClient.DEFAULT_EXCHANGE;
    private String amqpExchangeType = AmqpTransportClient.DEFAULT_EXCHANGE_TYPE;
    private AmqpTransportClient amqpTransport;

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
}
