package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.Locale;
import java.util.Optional;

public class PokerPayloadCodec {
  public static final String PROFILE = "UCW_POKER_V1";

  private final ObjectMapper objectMapper;

  public PokerPayloadCodec(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper;
  }

  public String encode(
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String playerId,
      int sequence,
      Object payload
  ) {
    PokerPayloadEvent event = new PokerPayloadEvent(
        PROFILE,
        tableId,
        handNumber,
        sequence,
        messageType == null ? null : messageType.name(),
        playerId,
        Instant.now(),
        objectMapper.valueToTree(payload)
    );
    try {
      return objectMapper.writeValueAsString(event);
    } catch (Exception exception) {
      throw new IllegalStateException("Failed to serialize poker payload", exception);
    }
  }

  public Optional<PokerPayloadEvent> parse(String payloadText) {
    if (payloadText == null || payloadText.isBlank()) {
      return Optional.empty();
    }

    try {
      PokerPayloadEvent event = objectMapper.readValue(payloadText, PokerPayloadEvent.class);
      if (isEnvelopeValid(event)) {
        return Optional.of(normalizeEventType(event));
      }
    } catch (Exception ignored) {
      // Fall back to legacy payload shape where message body is sent directly.
    }
    return parseLegacy(payloadText);
  }

  public Optional<MessageType> resolveMessageType(PokerPayloadEvent event) {
    if (event == null) {
      return Optional.empty();
    }
    return resolveMessageType(event.eventType());
  }

  public Optional<MessageType> resolveMessageType(String eventType) {
    if (eventType == null || eventType.isBlank()) {
      return Optional.empty();
    }
    try {
      return Optional.of(MessageType.valueOf(eventType.trim().toUpperCase(Locale.ROOT)));
    } catch (IllegalArgumentException ignored) {
      return Optional.empty();
    }
  }

  public <T> Optional<T> payloadAs(PokerPayloadEvent event, Class<T> payloadType) {
    if (event == null || event.payload() == null || event.payload().isNull()) {
      return Optional.empty();
    }
    try {
      return Optional.ofNullable(objectMapper.treeToValue(event.payload(), payloadType));
    } catch (Exception ignored) {
      return Optional.empty();
    }
  }

  private boolean isEnvelopeValid(PokerPayloadEvent event) {
    if (event == null || !PROFILE.equals(event.profile())) {
      return false;
    }
    if (event.sequence() == null || event.payload() == null) {
      return false;
    }
    return resolveMessageType(event.eventType()).isPresent();
  }

  private PokerPayloadEvent normalizeEventType(PokerPayloadEvent event) {
    MessageType messageType = resolveMessageType(event.eventType()).orElse(null);
    if (messageType == null) {
      return event;
    }
    return new PokerPayloadEvent(
        event.profile(),
        event.tableId(),
        event.handNumber(),
        event.sequence(),
        messageType.name(),
        event.playerId(),
        event.sentAt(),
        event.payload()
    );
  }

  private Optional<PokerPayloadEvent> parseLegacy(String payloadText) {
    try {
      JsonNode root = objectMapper.readTree(payloadText);
      MessageType messageType = resolveMessageType(root.path("type").asText(null)).orElse(null);
      if (messageType == null) {
        return Optional.empty();
      }

      JsonNode state = root.path("state");
      String tableId = firstNonBlank(textOrNull(root.path("tableId")), textOrNull(state.path("tableId")));
      Integer handNumber = firstNonNull(intOrNull(root.path("handNumber")), intOrNull(state.path("handNumber")));
      String playerId = textOrNull(root.path("playerId"));

      return Optional.of(new PokerPayloadEvent(
          PROFILE,
          tableId,
          handNumber,
          0,
          messageType.name(),
          playerId,
          Instant.now(),
          root
      ));
    } catch (Exception ignored) {
      return Optional.empty();
    }
  }

  private static String textOrNull(JsonNode node) {
    if (node == null || node.isNull() || node.isMissingNode()) {
      return null;
    }
    String text = node.asText(null);
    if (text == null || text.isBlank()) {
      return null;
    }
    return text;
  }

  private static Integer intOrNull(JsonNode node) {
    if (node == null || node.isNull() || node.isMissingNode()) {
      return null;
    }
    if (!node.canConvertToInt()) {
      return null;
    }
    return node.asInt();
  }

  private static <T> T firstNonNull(T first, T second) {
    return first != null ? first : second;
  }

  private static String firstNonBlank(String first, String second) {
    if (first != null && !first.isBlank()) {
      return first;
    }
    if (second != null && !second.isBlank()) {
      return second;
    }
    return null;
  }
}
