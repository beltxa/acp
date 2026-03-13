package com.cooperate.poker.common.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PlayerAction(
    @NotNull ActionType action,
    @Min(0) int amount,
    String reason
) {
}
