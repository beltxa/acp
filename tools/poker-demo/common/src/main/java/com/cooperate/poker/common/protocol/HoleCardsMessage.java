package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record HoleCardsMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @NotBlank String playerId,
    @NotNull List<String> holeCards
) {
  public HoleCardsMessage {
    holeCards = holeCards == null ? List.of() : List.copyOf(holeCards);
  }
}
