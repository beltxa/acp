package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record GameFinishedMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @NotBlank String winnerId,
    @NotNull Map<String, Integer> finalStacks,
    @Min(0) int totalHandsPlayed
) {
  public GameFinishedMessage {
    finalStacks = finalStacks == null ? Map.of() : Map.copyOf(finalStacks);
  }
}
