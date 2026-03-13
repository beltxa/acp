package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ActionResponseMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @NotBlank String playerId,
    @NotNull @Valid PlayerAction action
) {
}
