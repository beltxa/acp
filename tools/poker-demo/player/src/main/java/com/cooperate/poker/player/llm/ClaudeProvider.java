package com.cooperate.poker.player.llm;

import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Optional;

@Component
public class ClaudeProvider implements LLMProvider {
  @Override
  public String providerName() {
    return "claude";
  }

  @Override
  public Optional<String> generateDecision(String prompt, Duration timeout) {
    return Optional.empty();
  }
}
