package com.cooperate.poker.player.personality;

import com.cooperate.poker.common.model.PersonalityType;

public record Personality(
    PersonalityType type,
    double bluffFrequency,
    double aggressionFactor,
    String strategyHint
) {
}
