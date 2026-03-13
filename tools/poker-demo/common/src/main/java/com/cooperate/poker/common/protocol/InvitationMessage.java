package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record InvitationMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @NotBlank String playerId,
    @Min(1) int seatNumber
) {
}
