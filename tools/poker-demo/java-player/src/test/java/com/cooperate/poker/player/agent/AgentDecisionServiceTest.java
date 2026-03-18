package com.cooperate.poker.player.agent;

import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.PersonalityType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.RoundType;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.player.config.PlayerProperties;
import com.cooperate.poker.player.llm.LLMProvider;
import com.cooperate.poker.player.llm.ProviderSelector;
import com.cooperate.poker.player.personality.PersonalityResolver;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class AgentDecisionServiceTest {

  @Test
  void parsesValidJsonResponse() {
    AgentDecisionService service = createService(() -> Optional.of("{\"action\":\"CALL\",\"amount\":20,\"reason\":\"pot odds\"}"));

    ActionRequestMessage request = request(List.of(ActionType.FOLD, ActionType.CALL, ActionType.RAISE), 20, 0, 200);
    PlayerAction action = service.decideAction(request);

    assertThat(action.action()).isEqualTo(ActionType.CALL);
    assertThat(action.amount()).isEqualTo(20);
  }

  @Test
  void fallsBackOnInvalidJsonResponse() {
    AgentDecisionService service = createService(() -> Optional.of("not-json"));

    ActionRequestMessage request = request(List.of(ActionType.FOLD, ActionType.CALL), 25, 0, 300);
    PlayerAction action = service.decideAction(request);

    assertThat(action.action()).isEqualTo(ActionType.FOLD);
  }

  @Test
  void buildsPromptWithLegalActionsAndPersonality() {
    AgentDecisionService service = createService(Optional::empty);
    ActionRequestMessage request = request(List.of(ActionType.CHECK, ActionType.BET), 0, 0, 1000);

    String prompt = service.buildPrompt(request, new PersonalityResolver().resolve(PersonalityType.CONSERVATIVE, "Player-3"));

    assertThat(prompt).contains("legalActions=[CHECK, BET]");
    assertThat(prompt).contains("type=CONSERVATIVE");
  }

  private AgentDecisionService createService(ResponseFactory responseFactory) {
    PlayerProperties properties = new PlayerProperties();
    properties.setPlayerId("Player-1");
    properties.setPersonality(PersonalityType.TIGHT_AGGRESSIVE);

    LLMProvider provider = new LLMProvider() {
      @Override
      public String providerName() {
        return "stub";
      }

      @Override
      public Optional<String> generateDecision(String prompt, Duration timeout) {
        return responseFactory.response();
      }
    };

    ProviderSelector providerSelector = new ProviderSelector(List.of(provider), properties);
    return new AgentDecisionService(providerSelector, new PersonalityResolver(), properties);
  }

  private ActionRequestMessage request(List<ActionType> legal, int currentBet, int committedBet, int stack) {
    return new ActionRequestMessage(
        com.cooperate.poker.common.model.MessageType.ACTION_REQUEST,
        "table-1",
        2,
        RoundType.TURN,
        "Player-1",
        List.of("Ah", "Ks"),
        List.of("2c", "7d", "9h", "Tc"),
        120,
        currentBet,
        20,
        stack,
        committedBet,
        legal
    );
  }

  @FunctionalInterface
  private interface ResponseFactory {
    Optional<String> response();
  }
}
