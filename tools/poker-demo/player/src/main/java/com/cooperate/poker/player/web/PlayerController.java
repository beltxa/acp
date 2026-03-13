package com.cooperate.poker.player.web;

import com.cooperate.poker.common.protocol.ActionAppliedMessage;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.common.protocol.ActionResponseMessage;
import com.cooperate.poker.common.protocol.CommunityCardsUpdatedMessage;
import com.cooperate.poker.common.protocol.GameFinishedMessage;
import com.cooperate.poker.common.protocol.HandResultMessage;
import com.cooperate.poker.common.protocol.HandStartMessage;
import com.cooperate.poker.common.protocol.HoleCardsMessage;
import com.cooperate.poker.common.protocol.InvitationMessage;
import com.cooperate.poker.common.protocol.JoinTableMessage;
import com.cooperate.poker.common.protocol.PlayerEliminatedMessage;
import com.cooperate.poker.common.protocol.ProtocolPaths;
import com.cooperate.poker.player.service.PlayerService;
import jakarta.validation.Valid;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ConditionalOnProperty(name = "poker.player.transport-mode", havingValue = "HTTP")
public class PlayerController {
  private final PlayerService playerService;

  public PlayerController(PlayerService playerService) {
    this.playerService = playerService;
  }

  @PostMapping(ProtocolPaths.INVITATION)
  public JoinTableMessage invitation(@Valid @RequestBody InvitationMessage message) {
    return playerService.onInvitation(message);
  }

  @PostMapping(ProtocolPaths.HAND_START)
  public void handStart(@Valid @RequestBody HandStartMessage message) {
    playerService.onHandStart(message);
  }

  @PostMapping(ProtocolPaths.HOLE_CARDS)
  public void holeCards(@Valid @RequestBody HoleCardsMessage message) {
    playerService.onHoleCards(message);
  }

  @PostMapping(ProtocolPaths.ACTION_REQUEST)
  public ActionResponseMessage actionRequest(@Valid @RequestBody ActionRequestMessage message) {
    return playerService.onActionRequest(message);
  }

  @PostMapping(ProtocolPaths.ACTION_APPLIED)
  public void actionApplied(@Valid @RequestBody ActionAppliedMessage message) {
    playerService.onActionApplied(message);
  }

  @PostMapping(ProtocolPaths.COMMUNITY_CARDS_UPDATED)
  public void communityCardsUpdated(@Valid @RequestBody CommunityCardsUpdatedMessage message) {
    playerService.onCommunityCardsUpdated(message);
  }

  @PostMapping(ProtocolPaths.HAND_RESULT)
  public void handResult(@Valid @RequestBody HandResultMessage message) {
    playerService.onHandResult(message);
  }

  @PostMapping(ProtocolPaths.PLAYER_ELIMINATED)
  public void playerEliminated(@Valid @RequestBody PlayerEliminatedMessage message) {
    playerService.onPlayerEliminated(message);
  }

  @PostMapping(ProtocolPaths.GAME_FINISHED)
  public void gameFinished(@Valid @RequestBody GameFinishedMessage message) {
    playerService.onGameFinished(message);
  }
}
