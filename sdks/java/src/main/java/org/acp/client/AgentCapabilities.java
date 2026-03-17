/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AgentCapabilities {
    @JsonProperty("agent_id")
    private String agentId;
    @JsonProperty("protocol_versions")
    private List<String> protocolVersions = new ArrayList<>(List.of(AcpConstants.ACP_VERSION));
    @JsonProperty("crypto_suites")
    private List<String> cryptoSuites = new ArrayList<>(List.of(AcpConstants.DEFAULT_CRYPTO_SUITE));
    private List<String> transports = new ArrayList<>(List.of("https", "http", "relay", "amqp", "mqtt"));
    private Map<String, Boolean> supports = new LinkedHashMap<>(Map.of(
        "ack", true,
        "fail", true,
        "compensate", true,
        "direct_delivery", true,
        "relay_delivery", true,
        "amqp_delivery", true,
        "mqtt_delivery", true
    ));
    private Map<String, Integer> limits = new LinkedHashMap<>(Map.of("max_payload_bytes", 1048576));
    private List<String> profiles = new ArrayList<>(List.of("core", "self_asserted"));
    @JsonProperty("valid_until")
    private String validUntil = Instant.now().plus(365, ChronoUnit.DAYS).toString();

    public AgentCapabilities() {
    }

    public AgentCapabilities(String agentId) {
        this.agentId = agentId;
    }

    public static AgentCapabilities fromMap(Map<String, Object> value, String fallbackAgentId) {
        if (value == null) {
            return new AgentCapabilities(fallbackAgentId);
        }
        AgentCapabilities capabilities = JsonSupport.convert(value, AgentCapabilities.class);
        if (capabilities.agentId == null || capabilities.agentId.isBlank()) {
            capabilities.agentId = fallbackAgentId;
        }
        if (capabilities.protocolVersions == null || capabilities.protocolVersions.isEmpty()) {
            capabilities.protocolVersions = new ArrayList<>(List.of(AcpConstants.ACP_VERSION));
        }
        if (capabilities.cryptoSuites == null || capabilities.cryptoSuites.isEmpty()) {
            capabilities.cryptoSuites = new ArrayList<>(List.of(AcpConstants.DEFAULT_CRYPTO_SUITE));
        }
        if (capabilities.transports == null || capabilities.transports.isEmpty()) {
            capabilities.transports = new ArrayList<>(List.of("https", "http", "relay", "amqp", "mqtt"));
        }
        return capabilities;
    }

    public CapabilityMatch chooseCompatible(AgentCapabilities remote) {
        String protocolVersion = firstIntersection(protocolVersions, remote.protocolVersions);
        if (protocolVersion == null) {
            return CapabilityMatch.incompatible("No compatible protocol version");
        }
        String cryptoSuite = firstIntersection(cryptoSuites, remote.cryptoSuites);
        if (cryptoSuite == null) {
            return CapabilityMatch.incompatible("No compatible crypto suite");
        }
        String transport = firstIntersection(transports, remote.transports);
        if (transport == null) {
            return CapabilityMatch.incompatible("No compatible transport");
        }
        return CapabilityMatch.compatible(protocolVersion, cryptoSuite, transport);
    }

    private static String firstIntersection(List<String> local, List<String> remote) {
        if (local == null || remote == null) {
            return null;
        }
        for (String item : local) {
            if (remote.contains(item)) {
                return item;
            }
        }
        return null;
    }

    public Map<String, Object> toMap() {
        return JsonSupport.toMap(this);
    }

    public String getAgentId() {
        return agentId;
    }

    public void setAgentId(String agentId) {
        this.agentId = agentId;
    }

    public List<String> getProtocolVersions() {
        return protocolVersions;
    }

    public void setProtocolVersions(List<String> protocolVersions) {
        this.protocolVersions = protocolVersions;
    }

    public List<String> getCryptoSuites() {
        return cryptoSuites;
    }

    public void setCryptoSuites(List<String> cryptoSuites) {
        this.cryptoSuites = cryptoSuites;
    }

    public List<String> getTransports() {
        return transports;
    }

    public void setTransports(List<String> transports) {
        this.transports = transports;
    }

    public Map<String, Boolean> getSupports() {
        return supports;
    }

    public void setSupports(Map<String, Boolean> supports) {
        this.supports = supports;
    }

    public Map<String, Integer> getLimits() {
        return limits;
    }

    public void setLimits(Map<String, Integer> limits) {
        this.limits = limits;
    }

    public List<String> getProfiles() {
        return profiles;
    }

    public void setProfiles(List<String> profiles) {
        this.profiles = profiles;
    }

    public String getValidUntil() {
        return validUntil;
    }

    public void setValidUntil(String validUntil) {
        this.validUntil = validUntil;
    }

    public static final class CapabilityMatch {
        private final boolean compatible;
        private final String protocolVersion;
        private final String cryptoSuite;
        private final String transport;
        private final String reason;

        private CapabilityMatch(
            boolean compatible,
            String protocolVersion,
            String cryptoSuite,
            String transport,
            String reason
        ) {
            this.compatible = compatible;
            this.protocolVersion = protocolVersion;
            this.cryptoSuite = cryptoSuite;
            this.transport = transport;
            this.reason = reason;
        }

        public static CapabilityMatch compatible(String protocolVersion, String cryptoSuite, String transport) {
            return new CapabilityMatch(true, protocolVersion, cryptoSuite, transport, null);
        }

        public static CapabilityMatch incompatible(String reason) {
            return new CapabilityMatch(false, null, null, null, reason);
        }

        public boolean isCompatible() {
            return compatible;
        }

        public String getReason() {
            return reason;
        }

        public String getTransport() {
            return transport;
        }
    }
}
