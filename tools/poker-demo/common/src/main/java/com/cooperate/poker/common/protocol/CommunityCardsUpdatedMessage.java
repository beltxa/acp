package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.RoundType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CommunityCardsUpdatedMessage(
    @NotNull MessageType type,
    @NotBlank String tableId,
    @Min(0) int handNumber,
    @NotNull RoundType roundType,
    @NotNull List<String> communityCards
) {
  public CommunityCardsUpdatedMessage {
    communityCards = communityCards == null ? List.of() : List.copyOf(communityCards);
  }
}
