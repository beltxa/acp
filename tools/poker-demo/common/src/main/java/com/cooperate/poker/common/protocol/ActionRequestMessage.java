package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.RoundType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ActionRequestMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @Min(0) int handNumber,
    @NotNull RoundType roundType,
    @NotBlank String playerId,
    @NotNull List<String> holeCards,
    @NotNull List<String> communityCards,
    @Min(0) int pot,
    @Min(0) int currentBet,
    @Min(0) int minRaise,
    @Min(0) int stack,
    @Min(0) int committedBet,
    @NotNull List<ActionType> legalActions
) {
  public ActionRequestMessage {
    holeCards = holeCards == null ? List.of() : List.copyOf(holeCards);
    communityCards = communityCards == null ? List.of() : List.copyOf(communityCards);
    legalActions = legalActions == null ? List.of() : List.copyOf(legalActions);
  }
}
