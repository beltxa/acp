package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.GameState;
import com.cooperate.poker.common.model.MessageType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record HandStartMessage(
    @NotNull MessageType type,
    @NotNull @Valid GameState state
) {
}
