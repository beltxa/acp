package com.cooperate.poker.common.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record SeatState(
    @Min(1) int seatNumber,
    String playerId,
    boolean occupied
) {
}
