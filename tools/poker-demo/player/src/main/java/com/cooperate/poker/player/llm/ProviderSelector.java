package com.cooperate.poker.player.llm;

import com.cooperate.poker.player.config.PlayerProperties;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Locale;

@Component
public class ProviderSelector {
  private final List<LLMProvider> providers;
  private final PlayerProperties properties;

  public ProviderSelector(List<LLMProvider> providers, PlayerProperties properties) {
    this.providers = providers;
    this.properties = properties;
  }

  public LLMProvider activeProvider() {
    String configured = properties.getLlmProvider() == null
        ? "openai"
        : properties.getLlmProvider().toLowerCase(Locale.ROOT);

    return providers.stream()
        .filter(provider -> provider.providerName().equalsIgnoreCase(configured))
        .findFirst()
        .orElseGet(() -> providers.stream().findFirst().orElseThrow());
  }
}
