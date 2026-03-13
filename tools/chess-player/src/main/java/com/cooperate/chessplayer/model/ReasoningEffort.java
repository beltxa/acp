package com.cooperate.chessplayer.model;

import java.util.Locale;

public enum ReasoningEffort {
  LOW,
  MEDIUM,
  HIGH;

  public String apiValue() {
    return name().toLowerCase(Locale.ROOT);
  }

  public static ReasoningEffort fromValue(String value) {
    if (value == null || value.isBlank()) {
      return MEDIUM;
    }
    String normalized = value.trim().toUpperCase(Locale.ROOT);
    return switch (normalized) {
      case "LOW" -> LOW;
      case "MEDIUM" -> MEDIUM;
      case "HIGH" -> HIGH;
      default -> throw new IllegalArgumentException("unsupported reasoning effort: " + value);
    };
  }
}
