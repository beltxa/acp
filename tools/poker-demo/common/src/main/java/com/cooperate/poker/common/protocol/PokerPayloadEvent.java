package com.cooperate.poker.common.protocol;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import tools.jackson.databind.JsonNode;

import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PokerPayloadEvent(
    @JsonProperty("profile") String profile,
    @JsonProperty("table_id") String tableId,
    @JsonProperty("hand_number") Integer handNumber,
    @JsonProperty("sequence") Integer sequence,
    @JsonProperty("event_type") String eventType,
    @JsonProperty("player_id") String playerId,
    @JsonProperty("sent_at") Instant sentAt,
    @JsonProperty("payload") JsonNode payload
) {
}
