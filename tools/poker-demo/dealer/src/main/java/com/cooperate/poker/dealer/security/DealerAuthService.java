package com.cooperate.poker.dealer.security;

import com.cooperate.poker.dealer.config.DealerAuthProperties;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

@Service
public class DealerAuthService {
  private final DealerAuthProperties properties;

  public DealerAuthService(DealerAuthProperties properties) {
    this.properties = properties;
  }

  public boolean isEnabled() {
    return properties.isEnabled();
  }

  public String authenticate(String username, String password) {
    if (!properties.isEnabled()) {
      return null;
    }

    String configuredUsername = normalize(properties.getUsername());
    String configuredPassword = trimToNull(properties.getPassword());
    String candidateUsername = normalize(username);
    String candidatePassword = trimToNull(password);

    if (configuredUsername == null || configuredPassword == null || candidateUsername == null || candidatePassword == null) {
      return null;
    }

    if (!MessageDigest.isEqual(candidateUsername.getBytes(StandardCharsets.UTF_8), configuredUsername.getBytes(StandardCharsets.UTF_8))) {
      return null;
    }

    if (!MessageDigest.isEqual(candidatePassword.getBytes(StandardCharsets.UTF_8), configuredPassword.getBytes(StandardCharsets.UTF_8))) {
      return null;
    }

    return configuredUsername;
  }

  private static String normalize(String value) {
    String trimmed = trimToNull(value);
    return trimmed == null ? null : trimmed.toLowerCase(Locale.ROOT);
  }

  private static String trimToNull(String value) {
    if (value == null) {
      return null;
    }
    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
  }
}
