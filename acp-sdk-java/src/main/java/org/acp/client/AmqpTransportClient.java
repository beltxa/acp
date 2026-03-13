package org.acp.client;

import com.rabbitmq.client.AMQP;
import com.rabbitmq.client.Channel;
import com.rabbitmq.client.Connection;
import com.rabbitmq.client.ConnectionFactory;
import com.rabbitmq.client.GetResponse;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public class AmqpTransportClient {
    public static final String DEFAULT_EXCHANGE = "acp.exchange";
    public static final String DEFAULT_EXCHANGE_TYPE = "direct";

    private final String brokerUrl;
    private final String exchange;
    private final String exchangeType;
    private final int timeoutSeconds;

    public AmqpTransportClient(String brokerUrl) {
        this(brokerUrl, DEFAULT_EXCHANGE, DEFAULT_EXCHANGE_TYPE, 10);
    }

    public AmqpTransportClient(
        String brokerUrl,
        String exchange,
        String exchangeType,
        int timeoutSeconds
    ) {
        if (brokerUrl == null || brokerUrl.isBlank()) {
            throw new IllegalArgumentException("brokerUrl must be provided");
        }
        this.brokerUrl = brokerUrl;
        this.exchange = isBlank(exchange) ? DEFAULT_EXCHANGE : exchange;
        this.exchangeType = isBlank(exchangeType) ? DEFAULT_EXCHANGE_TYPE : exchangeType;
        this.timeoutSeconds = timeoutSeconds <= 0 ? 10 : timeoutSeconds;
    }

    public String getBrokerUrl() {
        return brokerUrl;
    }

    public String getExchange() {
        return exchange;
    }

    public String getExchangeType() {
        return exchangeType;
    }

    public int getTimeoutSeconds() {
        return timeoutSeconds;
    }

    public static String agentIdentifierToken(String agentId) {
        AgentIdentity.AgentIdParts parts = AgentIdentity.parseAgentId(agentId);
        String base = parts.domain() == null || parts.domain().isBlank()
            ? parts.name()
            : parts.name() + "." + parts.domain();
        String normalized = base.replaceAll("[^a-zA-Z0-9._-]+", ".");
        normalized = normalized.replaceAll("\\.+", ".");
        normalized = normalized.replaceAll("^\\.|\\.$", "");
        return normalized.isBlank() ? "unknown" : normalized;
    }

    public static String queueNameForAgent(String agentId) {
        return "acp.agent." + agentIdentifierToken(agentId);
    }

    public static String routingKeyForAgent(String agentId) {
        return "agent." + agentIdentifierToken(agentId);
    }

    public static Map<String, Object> buildServiceHint(String agentId, String brokerUrl, String exchange) {
        Map<String, Object> hint = new LinkedHashMap<>();
        hint.put("broker_url", brokerUrl);
        hint.put("exchange", isBlank(exchange) ? DEFAULT_EXCHANGE : exchange);
        hint.put("queue", queueNameForAgent(agentId));
        hint.put("routing_key", routingKeyForAgent(agentId));
        return hint;
    }

    public void publish(
        Map<String, Object> message,
        String recipientAgentId,
        Map<String, Object> amqpService
    ) {
        String targetBrokerUrl = pickString(amqpService, "broker_url", brokerUrl);
        String targetExchange = pickString(amqpService, "exchange", exchange);
        String targetQueue = pickString(amqpService, "queue", queueNameForAgent(recipientAgentId));
        String targetRoutingKey = pickString(amqpService, "routing_key", routingKeyForAgent(recipientAgentId));

        Map<String, Object> headers = metadataHeaders(message);
        String body = JsonSupport.toJson(message);

        try (Connection connection = openConnection(targetBrokerUrl);
             Channel channel = connection.createChannel()) {
            channel.exchangeDeclare(targetExchange, exchangeType, true);
            if (!isBlank(targetQueue)) {
                channel.queueDeclare(targetQueue, true, false, false, null);
                channel.queueBind(targetQueue, targetExchange, targetRoutingKey);
            }
            AMQP.BasicProperties properties = new AMQP.BasicProperties.Builder()
                .contentType("application/json")
                .deliveryMode(2)
                .headers(headers)
                .build();
            channel.basicPublish(
                targetExchange,
                targetRoutingKey,
                properties,
                body.getBytes(StandardCharsets.UTF_8)
            );
        } catch (Exception exc) {
            throw new IllegalStateException(
                "Failed to publish ACP message to AMQP recipient " + recipientAgentId + ": " + exc.getMessage(),
                exc
            );
        }
    }

    public int consume(
        String agentId,
        MessageHandler handler,
        Map<String, Object> amqpService,
        int maxMessages
    ) {
        Objects.requireNonNull(handler, "handler must be provided");
        String targetBrokerUrl = pickString(amqpService, "broker_url", brokerUrl);
        String targetExchange = pickString(amqpService, "exchange", exchange);
        String targetQueue = pickString(amqpService, "queue", queueNameForAgent(agentId));
        String targetRoutingKey = pickString(amqpService, "routing_key", routingKeyForAgent(agentId));
        int limit = maxMessages <= 0 ? Integer.MAX_VALUE : maxMessages;

        int processed = 0;
        try (Connection connection = openConnection(targetBrokerUrl);
             Channel channel = connection.createChannel()) {
            channel.exchangeDeclare(targetExchange, exchangeType, true);
            channel.queueDeclare(targetQueue, true, false, false, null);
            channel.queueBind(targetQueue, targetExchange, targetRoutingKey);

            while (processed < limit) {
                GetResponse delivery = channel.basicGet(targetQueue, false);
                if (delivery == null) {
                    break;
                }
                boolean ack = false;
                try {
                    Map<String, Object> message = JsonSupport.mapFromJson(
                        new String(delivery.getBody(), StandardCharsets.UTF_8)
                    );
                    ack = handler.handle(message);
                } catch (Exception ignored) {
                    ack = false;
                }
                if (ack) {
                    channel.basicAck(delivery.getEnvelope().getDeliveryTag(), false);
                } else {
                    channel.basicNack(delivery.getEnvelope().getDeliveryTag(), false, false);
                }
                processed++;
            }
        } catch (Exception exc) {
            throw new IllegalStateException("Failed consuming AMQP queue for " + agentId + ": " + exc.getMessage(), exc);
        }
        return processed;
    }

    protected Connection openConnection(String targetBrokerUrl) throws Exception {
        ConnectionFactory factory = new ConnectionFactory();
        factory.setUri(targetBrokerUrl);
        factory.setConnectionTimeout(timeoutSeconds * 1000);
        factory.setHandshakeTimeout(timeoutSeconds * 1000);
        return factory.newConnection();
    }

    public interface MessageHandler {
        boolean handle(Map<String, Object> message);
    }

    private static Map<String, Object> metadataHeaders(Map<String, Object> message) {
        Map<String, Object> headers = new LinkedHashMap<>();
        Map<String, Object> envelope = asMap(message.get("envelope"));
        copyHeader(envelope, headers, "acp_version", "acp_version");
        copyHeader(envelope, headers, "message_class", "acp_message_class");
        copyHeader(envelope, headers, "message_id", "acp_message_id");
        copyHeader(envelope, headers, "operation_id", "acp_operation_id");
        copyHeader(envelope, headers, "sender", "acp_sender");
        return headers;
    }

    private static void copyHeader(
        Map<String, Object> envelope,
        Map<String, Object> headers,
        String sourceField,
        String headerField
    ) {
        Object value = envelope.get(sourceField);
        if (value instanceof String str && !str.isBlank()) {
            headers.put(headerField, str);
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

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
