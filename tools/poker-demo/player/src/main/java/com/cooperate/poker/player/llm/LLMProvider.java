package com.cooperate.poker.player.llm;

import java.time.Duration;
import java.util.Optional;

public interface LLMProvider {
  String providerName();

  Optional<String> generateDecision(String prompt, Duration timeout);
}
