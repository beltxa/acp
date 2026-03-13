package com.cooperate.poker.common.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PlayerState(
    @NotBlank String playerId,
    @Min(0) int stack,
    @NotNull PlayerStatus status,
    @NotNull List<String> holeCards,
    @Min(0) int committedBet,
    int handDelta,
    int totalDelta,
    @Valid PlayerAction lastAction
) {
  public PlayerState {
    holeCards = holeCards == null ? List.of() : List.copyOf(holeCards);
  }
}
