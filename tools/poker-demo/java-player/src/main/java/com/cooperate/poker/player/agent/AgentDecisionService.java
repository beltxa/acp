package com.cooperate.poker.player.agent;

import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.player.config.PlayerProperties;
import com.cooperate.poker.player.llm.LLMProvider;
import com.cooperate.poker.player.llm.ProviderSelector;
import com.cooperate.poker.player.personality.Personality;
import com.cooperate.poker.player.personality.PersonalityResolver;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

@Service
public class AgentDecisionService {
  private final ObjectMapper objectMapper = JsonMapper.builder().findAndAddModules().build();
  private final ProviderSelector providerSelector;
  private final PersonalityResolver personalityResolver;
  private final PlayerProperties properties;

  public AgentDecisionService(
      ProviderSelector providerSelector,
      PersonalityResolver personalityResolver,
      PlayerProperties properties
  ) {
    this.providerSelector = providerSelector;
    this.personalityResolver = personalityResolver;
    this.properties = properties;
  }

  public PlayerAction decideAction(ActionRequestMessage requestMessage) {
    Personality personality = personalityResolver.resolve(properties.getPersonality(), properties.getPlayerId());
    LLMProvider provider = providerSelector.activeProvider();

    String prompt = buildPrompt(requestMessage, personality);
    Optional<String> rawResponse = provider.generateDecision(
        prompt,
        Duration.ofMillis(properties.getActionTimeoutMillis())
    );

    if (rawResponse.isPresent()) {
      Optional<PlayerAction> parsedAction = parseResponse(rawResponse.get(), requestMessage);
      if (parsedAction.isPresent()) {
        return parsedAction.get();
      }
      return safeFallback(requestMessage, "invalid-response-fallback");
    }

    return ruleBasedFallback(requestMessage, personality, "local-safe-policy");
  }

  public String buildPrompt(ActionRequestMessage requestMessage, Personality personality) {
    int toCall = Math.max(0, requestMessage.currentBet() - requestMessage.committedBet());

    return """
        Decide a single Texas Hold'em action for the current player.

        Constraints:
        - Return STRICT JSON object only.
        - Use one of legal actions exactly.
        - If action is BET or RAISE, amount must be total bet target for this round.

        JSON format:
        {"action":"FOLD|CHECK|CALL|BET|RAISE","amount":0,"reason":"short text"}

        Context:
        tableId=%s
        handNumber=%d
        round=%s
        playerId=%s
        holeCards=%s
        communityCards=%s
        pot=%d
        currentBet=%d
        committed=%d
        toCall=%d
        stack=%d
        minRaise=%d
        legalActions=%s

        Personality:
        type=%s
        bluffFrequency=%.2f
        aggressionFactor=%.2f
        strategyHint=%s
        """.formatted(
        requestMessage.tableId(),
        requestMessage.handNumber(),
        requestMessage.roundType(),
        requestMessage.playerId(),
        requestMessage.holeCards(),
        requestMessage.communityCards(),
        requestMessage.pot(),
        requestMessage.currentBet(),
        requestMessage.committedBet(),
        toCall,
        requestMessage.stack(),
        requestMessage.minRaise(),
        requestMessage.legalActions(),
        personality.type(),
        personality.bluffFrequency(),
        personality.aggressionFactor(),
        personality.strategyHint()
    );
  }

  public Optional<PlayerAction> parseResponse(String rawResponse, ActionRequestMessage requestMessage) {
    if (rawResponse == null || rawResponse.isBlank()) {
      return Optional.empty();
    }

    String trimmed = rawResponse.trim();
    String jsonSlice = trimmed;
    int startIndex = trimmed.indexOf('{');
    int endIndex = trimmed.lastIndexOf('}');
    if (startIndex >= 0 && endIndex > startIndex) {
      jsonSlice = trimmed.substring(startIndex, endIndex + 1);
    }

    try {
      JsonNode node = objectMapper.readTree(jsonSlice);
      String actionText = node.path("action").asText("");
      if (actionText.isBlank()) {
        return Optional.empty();
      }

      ActionType actionType = ActionType.valueOf(actionText.toUpperCase(Locale.ROOT));
      int amount = Math.max(0, node.path("amount").asInt(0));
      String reason = node.path("reason").asText(null);

      PlayerAction action = new PlayerAction(actionType, amount, reason);
      if (!isActionLegal(action, requestMessage)) {
        return Optional.empty();
      }

      return Optional.of(normalizeAction(action, requestMessage));
    } catch (Exception ignored) {
      return Optional.empty();
    }
  }

  private PlayerAction normalizeAction(PlayerAction action, ActionRequestMessage requestMessage) {
    int toCall = Math.max(0, requestMessage.currentBet() - requestMessage.committedBet());
    return switch (action.action()) {
      case FOLD -> new PlayerAction(ActionType.FOLD, 0, action.reason());
      case CHECK -> new PlayerAction(ActionType.CHECK, 0, action.reason());
      case CALL -> new PlayerAction(ActionType.CALL, Math.min(toCall, requestMessage.stack()), action.reason());
      case BET -> {
        int minTarget = Math.max(requestMessage.minRaise(), 1);
        int maxTarget = requestMessage.committedBet() + requestMessage.stack();
        int target = clamp(action.amount(), minTarget, maxTarget);
        yield new PlayerAction(ActionType.BET, target, action.reason());
      }
      case RAISE -> {
        int minTarget = requestMessage.currentBet() + requestMessage.minRaise();
        int maxTarget = requestMessage.committedBet() + requestMessage.stack();
        int target = clamp(action.amount(), minTarget, maxTarget);
        yield new PlayerAction(ActionType.RAISE, target, action.reason());
      }
    };
  }

  private boolean isActionLegal(PlayerAction action, ActionRequestMessage requestMessage) {
    List<ActionType> legalActions = requestMessage.legalActions();
    if (!legalActions.contains(action.action())) {
      return false;
    }

    int toCall = Math.max(0, requestMessage.currentBet() - requestMessage.committedBet());

    return switch (action.action()) {
      case FOLD -> true;
      case CHECK -> toCall == 0;
      case CALL -> requestMessage.stack() > 0;
      case BET -> requestMessage.currentBet() == 0 && requestMessage.stack() > 0;
      case RAISE -> requestMessage.currentBet() > 0 && requestMessage.stack() + requestMessage.committedBet() > requestMessage.currentBet();
    };
  }

  private PlayerAction ruleBasedFallback(ActionRequestMessage requestMessage, Personality personality, String reasonTag) {
    int toCall = Math.max(0, requestMessage.currentBet() - requestMessage.committedBet());
    boolean aggressive = personality.aggressionFactor() >= 0.7;
    boolean bluffing = personality.bluffFrequency() >= 0.3;

    if (toCall == 0) {
      if (requestMessage.legalActions().contains(ActionType.BET) && (aggressive || bluffing)) {
        int target = Math.min(
            requestMessage.committedBet() + requestMessage.stack(),
            Math.max(requestMessage.minRaise(), requestMessage.minRaise() + requestMessage.pot() / 6)
        );
        return new PlayerAction(ActionType.BET, target, reasonTag + ": pressure bet");
      }
      return new PlayerAction(ActionType.CHECK, 0, reasonTag + ": check");
    }

    if (requestMessage.legalActions().contains(ActionType.CALL) && aggressive && requestMessage.stack() > toCall) {
      return new PlayerAction(ActionType.CALL, Math.min(toCall, requestMessage.stack()), reasonTag + ": defend");
    }

    return new PlayerAction(ActionType.FOLD, 0, reasonTag + ": fold");
  }

  private PlayerAction safeFallback(ActionRequestMessage requestMessage, String reasonTag) {
    int toCall = Math.max(0, requestMessage.currentBet() - requestMessage.committedBet());
    if (toCall > 0 && requestMessage.legalActions().contains(ActionType.FOLD)) {
      return new PlayerAction(ActionType.FOLD, 0, reasonTag + ": fold");
    }
    if (requestMessage.legalActions().contains(ActionType.CHECK)) {
      return new PlayerAction(ActionType.CHECK, 0, reasonTag + ": check");
    }
    if (requestMessage.legalActions().contains(ActionType.CALL)) {
      return new PlayerAction(ActionType.CALL, Math.min(toCall, requestMessage.stack()), reasonTag + ": call");
    }
    return new PlayerAction(requestMessage.legalActions().getFirst(), 0, reasonTag + ": fallback");
  }

  private int clamp(int value, int min, int max) {
    return Math.max(min, Math.min(max, value));
  }
}
