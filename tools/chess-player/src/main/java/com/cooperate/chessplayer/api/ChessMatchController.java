package com.cooperate.chessplayer.api;

import com.cooperate.chessplayer.model.MatchState;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.cooperate.chessplayer.service.ChessMatchOrchestrator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/chess/matches")
public class ChessMatchController {
  private final ChessMatchOrchestrator orchestrator;

  public ChessMatchController(ChessMatchOrchestrator orchestrator) {
    this.orchestrator = orchestrator;
  }

  @PostMapping("/start")
  public ResponseEntity<StartMatchResponse> start(@RequestBody(required = false) StartMatchRequest request) {
    ReasoningEffort effort;
    try {
      effort = request == null ? orchestrator.getNextReasoningEffort() : ReasoningEffort.fromValue(request.reasoningEffort);
    } catch (IllegalArgumentException e) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
    }
    MatchState state = orchestrator.startMatch(effort);
    StartMatchResponse response = new StartMatchResponse();
    response.matchId = state.getMatchId();
    response.sessionId = state.getUcwId();
    response.status = state.getStatus().name();
    response.reasoningEffort = state.getReasoningEffort() == null ? null : state.getReasoningEffort().apiValue();
    return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
  }

  @GetMapping
  public ResponseEntity<List<MatchState>> list() {
    return ResponseEntity.ok(orchestrator.listMatches());
  }

  @GetMapping("/{matchId}")
  public ResponseEntity<MatchState> get(@PathVariable("matchId") UUID matchId) {
    return orchestrator.findMatch(matchId)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
  }

  public static class StartMatchRequest {
    @JsonProperty("reasoning_effort")
    public String reasoningEffort;
  }

  public static class StartMatchResponse {
    @JsonProperty("match_id")
    public UUID matchId;
    @JsonProperty("session_id")
    public UUID sessionId;
    @JsonProperty("status")
    public String status;
    @JsonProperty("reasoning_effort")
    public String reasoningEffort;
  }
}
