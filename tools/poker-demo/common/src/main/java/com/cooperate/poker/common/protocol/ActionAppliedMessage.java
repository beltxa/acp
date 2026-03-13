package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.RoundType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ActionAppliedMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @Min(0) int handNumber,
    @NotNull RoundType roundType,
    @NotBlank String playerId,
    @NotNull @Valid PlayerAction action,
    @Min(0) int updatedPot,
    @Min(0) int updatedStack,
    @Min(0) int updatedCurrentBet
) {
}
