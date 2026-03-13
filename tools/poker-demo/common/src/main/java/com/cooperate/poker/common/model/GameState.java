package com.cooperate.poker.common.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record GameState(
    @NotBlank String tableId,
    @Min(0) int handNumber,
    @NotNull RoundType roundType,
    @NotNull List<String> communityCards,
    @NotNull Map<String, @Valid PlayerState> playerStates,
    @Min(0) int potSize,
    @Min(0) int currentBet,
    @Min(0) int minRaise,
    String currentPlayer,
    @NotNull GameStatus status
) {
  public GameState {
    communityCards = communityCards == null ? List.of() : List.copyOf(communityCards);
    playerStates = playerStates == null ? Map.of() : Map.copyOf(playerStates);
  }
}
