package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class OpenAiChessMoveClient {
  private static final Logger log = LoggerFactory.getLogger(OpenAiChessMoveClient.class);
  private static final URI RESPONSES_API_URI = URI.create("https://api.openai.com/v1/responses");
  private static final Pattern UCI_MOVE_PATTERN = Pattern.compile("([a-h][1-8][a-h][1-8][qrbn]?)");

  private final ChessPlayerProperties properties;
  private final ObjectMapper objectMapper;
  private final HttpClient httpClient;

  public OpenAiChessMoveClient(ChessPlayerProperties properties, ObjectMapper objectMapper) {
    this.properties = properties;
    this.objectMapper = objectMapper;
    this.httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(8))
        .build();
  }

  public Optional<String> chooseMove(
      String fen,
      ChessColor sideToPlay,
      List<String> legalMovesUci,
      ReasoningEffort reasoningEffort
  ) {
    String apiKey = trimToNull(properties.getOpenaiApiKey());
    if (apiKey == null || legalMovesUci == null || legalMovesUci.isEmpty()) {
      return Optional.empty();
    }

    Set<String> legalMoves = new HashSet<>();
    for (String legalMove : legalMovesUci) {
      if (legalMove != null && !legalMove.isBlank()) {
        legalMoves.add(legalMove.trim().toLowerCase(Locale.ROOT));
      }
    }
    if (legalMoves.isEmpty()) {
      return Optional.empty();
    }

    String requestBody;
    try {
      requestBody = buildRequestPayload(fen, sideToPlay, legalMovesUci, reasoningEffort);
    } catch (Exception e) {
      log.warn("Failed to build OpenAI chess request payload", e);
      return Optional.empty();
    }

    try {
      HttpRequest request = HttpRequest.newBuilder(RESPONSES_API_URI)
          .header("Authorization", "Bearer " + apiKey)
          .header("Content-Type", "application/json")
          .timeout(Duration.ofSeconds(20))
          .POST(HttpRequest.BodyPublishers.ofString(requestBody, StandardCharsets.UTF_8))
          .build();
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        log.warn("OpenAI move request rejected with status {}", response.statusCode());
        return Optional.empty();
      }

      JsonNode root = objectMapper.readTree(response.body());
      String rawText = extractOutputText(root);
      if (rawText == null) {
        return Optional.empty();
      }
      return selectLegalMove(rawText, legalMoves);
    } catch (Exception e) {
      log.warn("OpenAI move request failed", e);
      return Optional.empty();
    }
  }

  private String buildRequestPayload(
      String fen,
      ChessColor sideToPlay,
      List<String> legalMovesUci,
      ReasoningEffort reasoningEffort
  ) throws Exception {
    ObjectNode payload = objectMapper.createObjectNode();
    payload.put("model", resolveModel(properties.getOpenaiModel()));
    payload.put("max_output_tokens", 24);
    payload.putObject("reasoning").put("effort", normalizeEffort(reasoningEffort).apiValue());
    payload.putObject("text").put("verbosity", "low");

    String systemPrompt = """
        You are a chess engine assistant.
        Return exactly one legal move in UCI format.
        Choose from the legal moves list only.
        Return only the move text and nothing else.
        """;
    String userPrompt = "FEN: " + fen + "\n"
        + "Side to move: " + (sideToPlay == null ? "unknown" : sideToPlay.name().toLowerCase(Locale.ROOT)) + "\n"
        + "Legal moves (UCI): " + String.join(" ", legalMovesUci);

    ArrayNode input = payload.putArray("input");
    input.addObject()
        .put("role", "system")
        .putArray("content")
        .addObject()
        .put("type", "input_text")
        .put("text", systemPrompt);
    input.addObject()
        .put("role", "user")
        .putArray("content")
        .addObject()
        .put("type", "input_text")
        .put("text", userPrompt);
    return objectMapper.writeValueAsString(payload);
  }

  private static Optional<String> selectLegalMove(String rawText, Set<String> legalMoves) {
    String normalizedText = rawText == null ? "" : rawText.trim().toLowerCase(Locale.ROOT);
    if (legalMoves.contains(normalizedText)) {
      return Optional.of(normalizedText);
    }

    Matcher matcher = UCI_MOVE_PATTERN.matcher(normalizedText);
    while (matcher.find()) {
      String candidate = matcher.group(1);
      if (legalMoves.contains(candidate)) {
        return Optional.of(candidate);
      }
    }
    return Optional.empty();
  }

  private static String extractOutputText(JsonNode root) {
    if (root == null) {
      return null;
    }

    JsonNode outputText = root.path("output_text");
    if (outputText.isTextual()) {
      return trimToNull(outputText.asText());
    }
    if (outputText.isArray()) {
      String joined = joinTextArray(outputText);
      if (joined != null) {
        return joined;
      }
    }

    JsonNode output = root.path("output");
    if (output.isArray()) {
      StringBuilder builder = new StringBuilder();
      for (JsonNode item : output) {
        JsonNode content = item.path("content");
        if (!content.isArray()) {
          continue;
        }
        for (JsonNode part : content) {
          String text = trimToNull(part.path("text").asText(null));
          if (text != null) {
            if (!builder.isEmpty()) {
              builder.append('\n');
            }
            builder.append(text);
          }
        }
      }
      return trimToNull(builder.toString());
    }
    return null;
  }

  private static String joinTextArray(JsonNode values) {
    StringBuilder builder = new StringBuilder();
    for (JsonNode value : values) {
      if (value != null && value.isTextual()) {
        String text = trimToNull(value.asText());
        if (text != null) {
          if (!builder.isEmpty()) {
            builder.append('\n');
          }
          builder.append(text);
        }
      }
    }
    return trimToNull(builder.toString());
  }

  private static ReasoningEffort normalizeEffort(ReasoningEffort reasoningEffort) {
    return reasoningEffort == null ? ReasoningEffort.MEDIUM : reasoningEffort;
  }

  private static String resolveModel(String configuredModel) {
    String value = trimToNull(configuredModel);
    if (value == null) {
      return "o3-mini";
    }
    String normalized = value.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]", "");
    if ("chatgpt3minio".equals(normalized)) {
      return "o3-mini";
    }
    return value;
  }

  private static String trimToNull(String value) {
    if (value == null) {
      return null;
    }
    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
  }
}
