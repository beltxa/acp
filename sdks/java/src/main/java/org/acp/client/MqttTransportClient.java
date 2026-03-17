/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import org.eclipse.paho.mqttv5.client.MqttClient;
import org.eclipse.paho.mqttv5.client.MqttConnectionOptions;
import org.eclipse.paho.mqttv5.common.MqttMessage;
import org.eclipse.paho.mqttv5.common.packet.MqttProperties;
import org.eclipse.paho.mqttv5.common.packet.UserProperty;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class MqttTransportClient {
    public static final int DEFAULT_QOS = 1;
    public static final String DEFAULT_TOPIC_PREFIX = "acp/agent";

    private final String brokerUrl;
    private final int qos;
    private final String topicPrefix;
    private final int timeoutSeconds;
    private final int keepAliveSeconds;

    public MqttTransportClient(String brokerUrl) {
        this(brokerUrl, DEFAULT_QOS, DEFAULT_TOPIC_PREFIX, 10, 30);
    }

    public MqttTransportClient(
        String brokerUrl,
        int qos,
        String topicPrefix,
        int timeoutSeconds,
        int keepAliveSeconds
    ) {
        if (brokerUrl == null || brokerUrl.isBlank()) {
            throw new IllegalArgumentException("brokerUrl must be provided");
        }
        this.brokerUrl = brokerUrl;
        this.qos = coerceQos(qos);
        this.topicPrefix = isBlank(topicPrefix) ? DEFAULT_TOPIC_PREFIX : topicPrefix;
        this.timeoutSeconds = timeoutSeconds <= 0 ? 10 : timeoutSeconds;
        this.keepAliveSeconds = keepAliveSeconds <= 0 ? 30 : keepAliveSeconds;
    }

    public String getBrokerUrl() {
        return brokerUrl;
    }

    public int getQos() {
        return qos;
    }

    public String getTopicPrefix() {
        return topicPrefix;
    }

    public int getTimeoutSeconds() {
        return timeoutSeconds;
    }

    public int getKeepAliveSeconds() {
        return keepAliveSeconds;
    }

    public static String agentIdentifierToken(String agentId) {
        AgentIdentity.AgentIdParts parts = AgentIdentity.parseAgentId(agentId);
        String base = parts.domain() == null || parts.domain().isBlank()
            ? parts.name()
            : parts.name() + "." + parts.domain();
        String normalized = base.replaceAll("[^a-zA-Z0-9._-]+", ".");
        normalized = normalized.replaceAll("\\.+", ".");
        normalized = normalized.replaceAll("^\\.|\\.$", "");
        normalized = normalized.toLowerCase();
        return normalized.isBlank() ? "unknown" : normalized;
    }

    public static String topicForAgent(String agentId) {
        return topicForAgent(agentId, DEFAULT_TOPIC_PREFIX);
    }

    public static String topicForAgent(String agentId, String topicPrefix) {
        String prefix = isBlank(topicPrefix) ? DEFAULT_TOPIC_PREFIX : topicPrefix;
        while (prefix.endsWith("/")) {
            prefix = prefix.substring(0, prefix.length() - 1);
        }
        return prefix + "/" + agentIdentifierToken(agentId);
    }

    public static Map<String, Object> buildServiceHint(
        String agentId,
        String brokerUrl
    ) {
        return buildServiceHint(agentId, brokerUrl, null, DEFAULT_QOS, DEFAULT_TOPIC_PREFIX);
    }

    public static Map<String, Object> buildServiceHint(
        String agentId,
        String brokerUrl,
        String topic,
        int qos,
        String topicPrefix
    ) {
        Map<String, Object> hint = new LinkedHashMap<>();
        hint.put("broker_url", brokerUrl);
        hint.put("topic", isBlank(topic) ? topicForAgent(agentId, topicPrefix) : topic);
        hint.put("qos", coerceQos(qos));
        return hint;
    }

    public void publish(
        Map<String, Object> message,
        String recipientAgentId,
        Map<String, Object> mqttService
    ) {
        String targetBrokerUrl = pickString(mqttService, "broker_url", brokerUrl);
        String targetTopic = pickString(
            mqttService,
            "topic",
            topicForAgent(recipientAgentId, topicPrefix)
        );
        int targetQos = coerceQos(
            mqttService == null ? qos : pickInteger(mqttService, "qos", qos)
        );

        String body = JsonSupport.toJson(message);
        Map<String, String> metadata = metadataProperties(message);

        MqttClient client = null;
        try {
            client = openClient(targetBrokerUrl);
            client.connect(connectionOptionsFor(targetBrokerUrl));
            MqttMessage mqttMessage = new MqttMessage(body.getBytes(StandardCharsets.UTF_8));
            mqttMessage.setQos(targetQos);
            mqttMessage.setRetained(false);
            MqttProperties properties = userProperties(metadata);
            if (properties != null) {
                mqttMessage.setProperties(properties);
            }
            client.publish(targetTopic, mqttMessage);
        } catch (Exception exc) {
            throw new IllegalStateException(
                "Failed to publish ACP message to MQTT recipient " + recipientAgentId + ": " + exc.getMessage(),
                exc
            );
        } finally {
            closeClientQuietly(client);
        }
    }

    public int consume(
        String agentId,
        MessageHandler handler,
        Map<String, Object> mqttService,
        int maxMessages
    ) {
        return consume(agentId, handler, mqttService, maxMessages, Duration.ofSeconds(1));
    }

    public int consume(
        String agentId,
        MessageHandler handler,
        Map<String, Object> mqttService,
        int maxMessages,
        Duration pollTimeout
    ) {
        Objects.requireNonNull(handler, "handler must be provided");
        String targetBrokerUrl = pickString(mqttService, "broker_url", brokerUrl);
        String targetTopic = pickString(mqttService, "topic", topicForAgent(agentId, topicPrefix));
        int targetQos = coerceQos(
            mqttService == null ? qos : pickInteger(mqttService, "qos", qos)
        );
        int limit = maxMessages <= 0 ? Integer.MAX_VALUE : maxMessages;
        long timeoutMillis = Math.max(10, pollTimeout == null ? 1000 : pollTimeout.toMillis());

        int processed = 0;
        LinkedBlockingQueue<MqttMessage> queue = new LinkedBlockingQueue<>();
        MqttClient client = null;
        try {
            client = openClient(targetBrokerUrl);
            client.setManualAcks(true);
            client.connect(connectionOptionsFor(targetBrokerUrl));
            client.subscribe(targetTopic, targetQos, (topic, message) -> queue.offer(message));

            while (processed < limit) {
                MqttMessage delivery = queue.poll(timeoutMillis, TimeUnit.MILLISECONDS);
                if (delivery == null) {
                    break;
                }

                boolean ack = false;
                try {
                    Map<String, Object> decoded = JsonSupport.mapFromJson(
                        new String(delivery.getPayload(), StandardCharsets.UTF_8)
                    );
                    ack = handler.handle(decoded);
                } catch (Exception ignored) {
                    ack = false;
                }

                if (ack) {
                    client.messageArrivedComplete(delivery.getId(), delivery.getQos());
                }
                processed++;
            }
            if (client.isConnected()) {
                client.unsubscribe(targetTopic);
            }
        } catch (Exception exc) {
            throw new IllegalStateException("Failed consuming MQTT topic for " + agentId + ": " + exc.getMessage(), exc);
        } finally {
            closeClientQuietly(client);
        }
        return processed;
    }

    protected MqttClient openClient(String targetBrokerUrl) throws Exception {
        String clientId = "acp-" + UUID.randomUUID().toString().replace("-", "");
        return new MqttClient(serverUriFor(targetBrokerUrl), clientId);
    }

    static Map<String, String> metadataProperties(Map<String, Object> message) {
        Map<String, String> properties = new LinkedHashMap<>();
        Map<String, Object> envelope = asMap(message.get("envelope"));
        copyProperty(envelope, properties, "acp_version", "acp_version");
        copyProperty(envelope, properties, "message_class", "acp_message_class");
        copyProperty(envelope, properties, "message_id", "acp_message_id");
        copyProperty(envelope, properties, "operation_id", "acp_operation_id");
        copyProperty(envelope, properties, "sender", "acp_sender");
        return properties;
    }

    private MqttConnectionOptions connectionOptionsFor(String targetBrokerUrl) {
        URI uri = URI.create(targetBrokerUrl);
        MqttConnectionOptions options = new MqttConnectionOptions();
        options.setConnectionTimeout(timeoutSeconds);
        options.setKeepAliveInterval(keepAliveSeconds);
        if (!isBlank(uri.getUserInfo())) {
            String[] userInfoParts = uri.getUserInfo().split(":", 2);
            String username = decodeUrl(userInfoParts[0]);
            String password = userInfoParts.length > 1 ? decodeUrl(userInfoParts[1]) : "";
            options.setUserName(username);
            options.setPassword(password.getBytes(StandardCharsets.UTF_8));
        }
        return options;
    }

    private static String serverUriFor(String rawBrokerUrl) {
        URI uri = URI.create(rawBrokerUrl);
        String scheme = uri.getScheme() == null ? "mqtt" : uri.getScheme().toLowerCase();
        String host = uri.getHost();
        if (isBlank(host)) {
            throw new IllegalArgumentException("Invalid MQTT broker_url: " + rawBrokerUrl);
        }
        int port = uri.getPort();
        if (port <= 0) {
            port = switch (scheme) {
                case "mqtts", "ssl" -> 8883;
                case "ws" -> 80;
                case "wss" -> 443;
                default -> 1883;
            };
        }
        String translatedScheme = switch (scheme) {
            case "mqtt" -> "tcp";
            case "mqtts", "ssl" -> "ssl";
            case "ws" -> "ws";
            case "wss" -> "wss";
            case "tcp" -> "tcp";
            default -> throw new IllegalArgumentException("Unsupported MQTT broker_url scheme: " + scheme);
        };
        String path = ("ws".equals(translatedScheme) || "wss".equals(translatedScheme))
            ? (isBlank(uri.getPath()) ? "/mqtt" : uri.getPath())
            : "";
        return translatedScheme + "://" + host + ":" + port + path;
    }

    private static MqttProperties userProperties(Map<String, String> metadata) {
        if (metadata.isEmpty()) {
            return null;
        }
        MqttProperties properties = new MqttProperties();
        List<UserProperty> userProperties = new ArrayList<>();
        for (Map.Entry<String, String> entry : metadata.entrySet()) {
            userProperties.add(new UserProperty(entry.getKey(), entry.getValue()));
        }
        properties.setUserProperties(userProperties);
        return properties;
    }

    private static void copyProperty(
        Map<String, Object> envelope,
        Map<String, String> properties,
        String sourceField,
        String destinationField
    ) {
        Object value = envelope.get(sourceField);
        if (value instanceof String str && !str.isBlank()) {
            properties.put(destinationField, str);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> raw) {
            return (Map<String, Object>) raw;
        }
        return Map.of();
    }

    private static String pickString(Map<String, Object> map, String key, String fallback) {
        if (map != null) {
            Object value = map.get(key);
            if (value instanceof String str && !str.isBlank()) {
                return str;
            }
        }
        return fallback;
    }

    private static int pickInteger(Map<String, Object> map, String key, int fallback) {
        if (map != null) {
            Object value = map.get(key);
            if (value instanceof Number number) {
                return number.intValue();
            }
            if (value instanceof String str) {
                try {
                    return Integer.parseInt(str);
                } catch (NumberFormatException ignored) {
                    return fallback;
                }
            }
        }
        return fallback;
    }

    private static int coerceQos(int value) {
        if (value < 0 || value > 2) {
            return DEFAULT_QOS;
        }
        return value;
    }

    private static String decodeUrl(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }

    private static void closeClientQuietly(MqttClient client) {
        if (client == null) {
            return;
        }
        try {
            if (client.isConnected()) {
                client.disconnect();
            }
        } catch (Exception ignored) {
            // no-op
        }
        try {
            client.close();
        } catch (Exception ignored) {
            // no-op
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    public interface MessageHandler {
        boolean handle(Map<String, Object> message);
    }
}
