package com.cooperate.poker.common.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record TableState(
    @NotBlank String tableId,
    @NotNull GameStatus status,
    @NotNull List<@Valid SeatState> seats,
    @NotNull @Valid GameState gameState,
    @NotNull List<String> actionLog,
    @NotNull List<String> reasoningLog
) {
  public TableState {
    seats = seats == null ? List.of() : List.copyOf(seats);
    actionLog = actionLog == null ? List.of() : List.copyOf(actionLog);
    reasoningLog = reasoningLog == null ? List.of() : List.copyOf(reasoningLog);
  }
}
