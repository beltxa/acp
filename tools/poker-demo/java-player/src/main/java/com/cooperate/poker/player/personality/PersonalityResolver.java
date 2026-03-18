package com.cooperate.poker.player.personality;

import com.cooperate.poker.common.model.PersonalityType;
import org.springframework.stereotype.Component;

@Component
public class PersonalityResolver {

  public Personality resolve(PersonalityType configuredType, String playerId) {
    PersonalityType type = configuredType != null ? configuredType : defaultTypeForPlayer(playerId);
    return switch (type) {
      case TIGHT_AGGRESSIVE -> new Personality(type, 0.10, 0.78, "Play strong ranges and pressure with value-heavy raises.");
      case LOOSE_AGGRESSIVE -> new Personality(type, 0.25, 0.88, "Contest many pots and apply pressure often.");
      case CONSERVATIVE -> new Personality(type, 0.05, 0.35, "Avoid marginal spots and preserve stack.");
      case CHAOTIC -> new Personality(type, 0.45, 0.92, "Mix in unpredictable aggression and occasional bluffs.");
    };
  }

  private PersonalityType defaultTypeForPlayer(String playerId) {
    if ("Player-1".equalsIgnoreCase(playerId)) {
      return PersonalityType.TIGHT_AGGRESSIVE;
    }
    if ("Player-2".equalsIgnoreCase(playerId)) {
      return PersonalityType.LOOSE_AGGRESSIVE;
    }
    if ("Player-3".equalsIgnoreCase(playerId)) {
      return PersonalityType.CONSERVATIVE;
    }
    return PersonalityType.CHAOTIC;
  }
}
