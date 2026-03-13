package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record HandResultMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @Min(0) int handNumber,
    @NotNull List<String> winnerIds,
    @NotBlank String handCategory,
    @Min(0) int potSize,
    @NotNull Map<String, Integer> amountWonByPlayer,
    @NotNull Map<String, Integer> updatedStacks
) {
  public HandResultMessage {
    winnerIds = winnerIds == null ? List.of() : List.copyOf(winnerIds);
    amountWonByPlayer = amountWonByPlayer == null ? Map.of() : Map.copyOf(amountWonByPlayer);
    updatedStacks = updatedStacks == null ? Map.of() : Map.copyOf(updatedStacks);
  }
}
