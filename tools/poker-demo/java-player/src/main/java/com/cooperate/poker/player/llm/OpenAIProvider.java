package com.cooperate.poker.player.llm;

import com.cooperate.poker.player.config.PlayerProperties;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;

@Component
public class OpenAIProvider implements LLMProvider {
  private static final Logger log = LoggerFactory.getLogger(OpenAIProvider.class);
  private static final URI RESPONSES_API_URI = URI.create("https://api.openai.com/v1/responses");

  private final PlayerProperties properties;
  private final ObjectMapper objectMapper;
  private final HttpClient httpClient;

  public OpenAIProvider(PlayerProperties properties) {
    this.properties = properties;
    this.objectMapper = JsonMapper.builder().findAndAddModules().build();
    this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();
  }

  @Override
  public String providerName() {
    return "openai";
  }

  @Override
  public Optional<String> generateDecision(String prompt, Duration timeout) {
    String apiKey = trimToNull(properties.getOpenaiApiKey());
    if (apiKey == null || prompt == null || prompt.isBlank()) {
      return Optional.empty();
    }

    try {
      String body = buildRequestPayload(prompt);
      HttpRequest request = HttpRequest.newBuilder(RESPONSES_API_URI)
          .header("Authorization", "Bearer " + apiKey)
          .header("Content-Type", "application/json")
          .timeout(timeout)
          .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
          .build();
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        log.warn("OpenAI decision request failed with status {}", response.statusCode());
        return Optional.empty();
      }

      JsonNode root = objectMapper.readTree(response.body());
      return extractOutputText(root);
    } catch (Exception exception) {
      log.warn("OpenAI decision request failed", exception);
      return Optional.empty();
    }
  }

  private String buildRequestPayload(String prompt) throws Exception {
    ObjectNode payload = objectMapper.createObjectNode();
    payload.put("model", resolveModel(properties.getModel()));
    payload.put("max_output_tokens", 220);
    payload.putObject("text").put("verbosity", "low");

    ArrayNode input = payload.putArray("input");
    input.addObject()
        .put("role", "system")
        .putArray("content")
        .addObject()
        .put("type", "input_text")
        .put("text", "You are a poker decision engine. Return strict JSON only.");
    input.addObject()
        .put("role", "user")
        .putArray("content")
        .addObject()
        .put("type", "input_text")
        .put("text", prompt);

    return objectMapper.writeValueAsString(payload);
  }

  private Optional<String> extractOutputText(JsonNode root) {
    if (root == null) {
      return Optional.empty();
    }

    JsonNode outputText = root.path("output_text");
    if (outputText.isTextual()) {
      return Optional.ofNullable(trimToNull(outputText.asText()));
    }

    JsonNode output = root.path("output");
    if (output.isArray()) {
      StringBuilder builder = new StringBuilder();
      for (JsonNode item : output) {
        JsonNode content = item.path("content");
        if (!content.isArray()) {
          continue;
        }
        for (JsonNode piece : content) {
          String text = trimToNull(piece.path("text").asText(null));
          if (text == null) {
            continue;
          }
          if (!builder.isEmpty()) {
            builder.append('\n');
          }
          builder.append(text);
        }
      }
      return Optional.ofNullable(trimToNull(builder.toString()));
    }

    return Optional.empty();
  }

  private static String resolveModel(String configuredModel) {
    String model = trimToNull(configuredModel);
    return model == null ? "chatgpt-5.2-instant" : model;
  }

  private static String trimToNull(String value) {
    if (value == null) {
      return null;
    }
    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
  }
}
