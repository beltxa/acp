package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.ChessPayloadEvent;
import com.cooperate.chessplayer.model.GameOutcome;
import com.cooperate.chessplayer.model.MatchState;
import com.cooperate.chessplayer.model.MatchStateStatus;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.github.bhlangonijr.chesslib.Board;
import com.github.bhlangonijr.chesslib.Piece;
import com.github.bhlangonijr.chesslib.PieceType;
import com.github.bhlangonijr.chesslib.Side;
import com.github.bhlangonijr.chesslib.Square;
import com.github.bhlangonijr.chesslib.move.Move;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Service
public class ChessMatchOrchestrator {
  private static final Logger log = LoggerFactory.getLogger(ChessMatchOrchestrator.class);

  private final ChessPlayerProperties properties;
  private final AcpChessClient acpChessClient;
  private final ChessEngineService chessEngineService;
  private final ChessPayloadCodec payloadCodec;
  private final MatchStateStore matchStateStore;
  private final PgnExporter pgnExporter;
  private ReasoningEffort nextReasoningEffort;

  public ChessMatchOrchestrator(
      ChessPlayerProperties properties,
      AcpChessClient acpChessClient,
      ChessEngineService chessEngineService,
      ChessPayloadCodec payloadCodec,
      MatchStateStore matchStateStore,
      PgnExporter pgnExporter
  ) {
    this.properties = properties;
    this.acpChessClient = acpChessClient;
    this.chessEngineService = chessEngineService;
    this.payloadCodec = payloadCodec;
    this.matchStateStore = matchStateStore;
    this.pgnExporter = pgnExporter;
    this.nextReasoningEffort = normalizeEffort(properties.getReasoningEffort());
  }

  @PostConstruct
  public void startupLog() {
    log.info(
        "Chess player starting: role={}, color={}, localAgentId={}, remoteAgentId={}, endpoint={}, openaiModel={}, openaiKeyConfigured={}, reasoningEffort={}",
        properties.getRole(),
        properties.getColor(),
        properties.getLocalAgentId(),
        properties.getRemoteAgentId(),
        properties.resolveAcpEndpoint(),
        properties.getOpenaiModel(),
        properties.getOpenaiApiKey() != null && !properties.getOpenaiApiKey().isBlank(),
        nextReasoningEffort
    );
  }

  public synchronized MatchState startMatch() {
    return startMatch(nextReasoningEffort);
  }

  public synchronized MatchState startMatch(ReasoningEffort reasoningEffort) {
    ReasoningEffort matchEffort = normalizeEffort(reasoningEffort);
    UUID matchId = UUID.randomUUID();

    MatchState state = new MatchState();
    state.setUcwId(matchId);
    state.setMatchId(matchId);
    state.setLocalColor(properties.getColor());
    state.setLocalParticipantUrn(properties.getLocalAgentId());
    state.setRemoteParticipantUrn(properties.getRemoteAgentId());
    state.setLocalUserUrn(properties.getLocalDisplayName());
    state.setRemoteUserUrn(properties.getRemoteDisplayName());
    state.setReasoningEffort(matchEffort);
    state.setCurrentFen(chessEngineService.initialFen());
    state.setUcwStatus("ACTIVE");
    state.setStatus(MatchStateStatus.ACTIVE);
    state.setOutcome(GameOutcome.ONGOING);
    state.setCreatedAt(Instant.now());
    state.setUpdatedAt(Instant.now());
    matchStateStore.upsert(state);
    log.info("Started ACP chess match {}", matchId);
    return state;
  }

  public synchronized ReasoningEffort getNextReasoningEffort() {
    return nextReasoningEffort;
  }

  public synchronized void setNextReasoningEffort(ReasoningEffort effort) {
    ReasoningEffort normalized = normalizeEffort(effort);
    if (hasInProgressMatches()) {
      throw new IllegalStateException("reasoning effort cannot change while a match is active");
    }
    this.nextReasoningEffort = normalized;
    properties.setReasoningEffort(normalized);
  }

  public List<MatchState> listMatches() {
    return matchStateStore.list();
  }

  public Optional<MatchState> findMatch(UUID ucwId) {
    return matchStateStore.find(ucwId);
  }

  public synchronized void onInboundPayload(Map<String, Object> payload) {
    Optional<ChessPayloadEvent> parsed = payloadCodec.parse(payload);
    if (parsed.isEmpty()) {
      return;
    }
    ChessPayloadEvent event = parsed.get();
    MatchState state = findOrCreateState(event);
    applyEvent(state, event);
    finalizeIfCompleted(state);
    matchStateStore.upsert(state);
  }

  @Scheduled(fixedDelayString = "${cooperate.chess.pollIntervalMs:2000}")
  public synchronized void poll() {
    try {
      for (MatchState state : matchStateStore.list()) {
        processMatch(state);
      }
    } catch (Exception e) {
      log.warn("Chess poll cycle failed", e);
    }
  }

  private void processMatch(MatchState state) {
    if (state == null || state.getUcwId() == null) {
      return;
    }
    if (state.getReasoningEffort() == null) {
      state.setReasoningEffort(nextReasoningEffort);
    }
    if (state.getCurrentFen() == null || state.getCurrentFen().isBlank()) {
      state.setCurrentFen(chessEngineService.initialFen());
    }

    if (state.getOutcome() == null) {
      state.setOutcome(GameOutcome.ONGOING);
    }

    if (state.getOutcome() == GameOutcome.ONGOING) {
      applyTimeoutPolicy(state);
      ChessEngineService.PositionAssessment assessment =
          chessEngineService.assess(state.getCurrentFen(), state.getMoveHistoryUci().size(), properties.getMaxPlies());
      if (assessment.outcome().isTerminal()) {
        state.setOutcome(assessment.outcome());
        state.setOutcomeReason(assessment.reason());
      }
    }

    if (state.getOutcome().isTerminal()) {
      sendGameEndIfNeeded(state);
      finalizeIfCompleted(state);
      matchStateStore.upsert(state);
      return;
    }

    Board board = chessEngineService.loadBoard(state.getCurrentFen());
    ChessColor sideToMove = ChessColor.fromSide(board.getSideToMove());
    if (sideToMove != state.getLocalColor()) {
      state.setStatus(MatchStateStatus.ACTIVE);
      state.setUcwStatus("ACTIVE");
      matchStateStore.upsert(state);
      return;
    }

    ChessEngineService.MoveDecision decision;
    try {
      decision = chessEngineService.nextMove(
          state.getCurrentFen(),
          state.getLocalColor(),
          normalizeEffort(state.getReasoningEffort())
      );
    } catch (Exception e) {
      log.warn("Unable to compute next move for match {}", state.getMatchId(), e);
      return;
    }

    if (!waitBeforeMoveSubmit(state.getMatchId())) {
      return;
    }

    int nextSequence = state.getLatestSequence() + 1;
    Optional<ChessPayloadEvent> maybeEvent = payloadCodec.parse(
        payloadCodec.toMovePayload(
            state.getMatchId(),
            nextSequence,
            decision.nextToMove(),
            decision.uci(),
            decision.fenAfter()
        )
    );
    if (maybeEvent.isEmpty()) {
      return;
    }

    if (!acpChessClient.sendChessEvent(maybeEvent.get())) {
      return;
    }
    applyEvent(state, maybeEvent.get());

    ChessEngineService.PositionAssessment assessment =
        chessEngineService.assess(state.getCurrentFen(), state.getMoveHistoryUci().size(), properties.getMaxPlies());
    if (assessment.outcome().isTerminal()) {
      state.setOutcome(assessment.outcome());
      state.setOutcomeReason(assessment.reason());
      sendGameEndIfNeeded(state);
    }
    finalizeIfCompleted(state);
    matchStateStore.upsert(state);
  }

  private MatchState findOrCreateState(ChessPayloadEvent event) {
    for (MatchState state : matchStateStore.list()) {
      if (state != null && event.matchId != null && event.matchId.equals(state.getMatchId())) {
        return state;
      }
    }
    MatchState state = new MatchState();
    UUID matchId = event.matchId == null ? UUID.randomUUID() : event.matchId;
    state.setUcwId(matchId);
    state.setMatchId(matchId);
    state.setLocalColor(properties.getColor());
    state.setLocalParticipantUrn(properties.getLocalAgentId());
    state.setRemoteParticipantUrn(properties.getRemoteAgentId());
    state.setLocalUserUrn(properties.getLocalDisplayName());
    state.setRemoteUserUrn(properties.getRemoteDisplayName());
    state.setReasoningEffort(nextReasoningEffort);
    state.setCurrentFen(chessEngineService.initialFen());
    state.setUcwStatus("ACTIVE");
    state.setStatus(MatchStateStatus.ACTIVE);
    state.setOutcome(GameOutcome.ONGOING);
    state.setCreatedAt(Instant.now());
    state.setUpdatedAt(Instant.now());
    return state;
  }

  private void applyEvent(MatchState state, ChessPayloadEvent event) {
    if (state == null || event == null || event.sequence == null || event.sequence <= state.getLatestSequence()) {
      return;
    }
    if (event.matchId != null) {
      state.setMatchId(event.matchId);
      state.setUcwId(event.matchId);
    }
    if (state.getCurrentFen() == null || state.getCurrentFen().isBlank()) {
      state.setCurrentFen(chessEngineService.initialFen());
    }
    Board board = chessEngineService.loadBoard(state.getCurrentFen());

    if (ChessPayloadCodec.EVENT_MOVE.equals(event.eventType) && event.move != null && event.move.uci != null) {
      boolean applied = applyUciMove(board, event.move.uci);
      if (!applied && event.fenAfter != null && !event.fenAfter.isBlank()) {
        board.loadFromFen(event.fenAfter);
        applied = true;
      }
      if (!applied) {
        log.warn("Unable to apply inbound move {} for match {}", event.move.uci, state.getMatchId());
        return;
      }
      List<String> moves = state.getMoveHistoryUci() == null ? new ArrayList<>() : new ArrayList<>(state.getMoveHistoryUci());
      moves.add(event.move.uci);
      state.setMoveHistoryUci(moves);
      state.setCurrentFen(board.getFen());
      state.setLatestSequence(event.sequence);
      state.setLastActionAt(Instant.now());
      state.setStatus(MatchStateStatus.ACTIVE);
      state.setUcwStatus("ACTIVE");
      return;
    }

    if (ChessPayloadCodec.EVENT_GAME_END.equals(event.eventType)) {
      if (event.fenAfter != null && !event.fenAfter.isBlank()) {
        board.loadFromFen(event.fenAfter);
      }
      state.setCurrentFen(board.getFen());
      state.setLatestSequence(event.sequence);
      if (event.result != null) {
        state.setOutcome(parseOutcome(event.result));
      }
      state.setOutcomeReason(event.reason);
      state.setStatus(MatchStateStatus.COMPLETED);
      state.setUcwStatus("COMPLETED");
      state.setCompletionProposalSent(true);
    }
  }

  private boolean waitBeforeMoveSubmit(UUID matchId) {
    long delayMs = Math.max(0L, properties.getMoveSendDelayMs());
    if (delayMs <= 0L) {
      return true;
    }
    try {
      Thread.sleep(delayMs);
      return true;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      log.warn("Interrupted while delaying move submission for match {}", matchId);
      return false;
    }
  }

  private void sendGameEndIfNeeded(MatchState state) {
    if (state == null || state.getOutcome() == null || !state.getOutcome().isTerminal() || state.isCompletionProposalSent()) {
      return;
    }
    int nextSequence = state.getLatestSequence() + 1;
    String winnerAgentId = winnerAgentId(state);
    Optional<ChessPayloadEvent> maybeEvent = payloadCodec.parse(
        payloadCodec.toGameEndPayload(
            state.getMatchId(),
            nextSequence,
            state.getOutcome(),
            state.getOutcomeReason(),
            winnerAgentId,
            state.getCurrentFen()
        )
    );
    if (maybeEvent.isEmpty()) {
      return;
    }
    if (!acpChessClient.sendChessEvent(maybeEvent.get())) {
      state.setStatus(MatchStateStatus.COMPLETING);
      state.setUcwStatus("ACTIVE");
      return;
    }
    applyEvent(state, maybeEvent.get());
    state.setCompletionProposalSent(true);
    state.setLastActionAt(Instant.now());
  }

  private String winnerAgentId(MatchState state) {
    if (state.getOutcome() == GameOutcome.WHITE_WIN) {
      return state.getLocalColor() == ChessColor.WHITE ? state.getLocalParticipantUrn() : state.getRemoteParticipantUrn();
    }
    if (state.getOutcome() == GameOutcome.BLACK_WIN) {
      return state.getLocalColor() == ChessColor.BLACK ? state.getLocalParticipantUrn() : state.getRemoteParticipantUrn();
    }
    return null;
  }

  private void applyTimeoutPolicy(MatchState state) {
    if (state.getCreatedAt() == null || state.getOutcome().isTerminal()) {
      return;
    }
    Duration elapsed = Duration.between(state.getCreatedAt(), Instant.now());
    if (elapsed.getSeconds() >= properties.getMatchTimeoutSeconds()) {
      state.setOutcome(GameOutcome.DRAW);
      state.setOutcomeReason("TIMEOUT");
    }
  }

  private void finalizeIfCompleted(MatchState state) {
    if (state.getOutcome() == null || !state.getOutcome().isTerminal()) {
      state.setStatus(MatchStateStatus.ACTIVE);
      state.setUcwStatus("ACTIVE");
      return;
    }
    if (state.isCompletionProposalSent()) {
      state.setStatus(MatchStateStatus.COMPLETED);
      state.setUcwStatus("COMPLETED");
      if (!state.isPgnExported()) {
        pgnExporter.export(state);
        state.setPgnExported(true);
      }
      return;
    }
    state.setStatus(MatchStateStatus.COMPLETING);
    state.setUcwStatus("ACTIVE");
  }

  private boolean applyUciMove(Board board, String uci) {
    if (uci == null || uci.length() < 4) {
      return false;
    }
    try {
      String fromToken = uci.substring(0, 2).toUpperCase();
      String toToken = uci.substring(2, 4).toUpperCase();
      Square from = Square.fromValue(fromToken);
      Square to = Square.fromValue(toToken);
      if (from == null || to == null || from == Square.NONE || to == Square.NONE) {
        return false;
      }

      Move move;
      if (uci.length() >= 5) {
        Piece promotion = parsePromotionPiece(uci.charAt(4), board.getSideToMove());
        if (promotion == Piece.NONE) {
          return false;
        }
        move = new Move(from, to, promotion);
      } else {
        move = new Move(from, to);
      }
      return board.doMove(move);
    } catch (RuntimeException e) {
      log.debug("Unable to apply move {}; will try fen fallback", uci, e);
      return false;
    }
  }

  private static Piece parsePromotionPiece(char value, Side side) {
    PieceType pieceType = switch (Character.toLowerCase(value)) {
      case 'q' -> PieceType.QUEEN;
      case 'r' -> PieceType.ROOK;
      case 'b' -> PieceType.BISHOP;
      case 'n' -> PieceType.KNIGHT;
      default -> PieceType.NONE;
    };
    if (pieceType == PieceType.NONE) {
      return Piece.NONE;
    }
    return Piece.make(side, pieceType);
  }

  private static GameOutcome parseOutcome(String value) {
    return switch (value == null ? "" : value.trim().toUpperCase()) {
      case "WHITE_WIN" -> GameOutcome.WHITE_WIN;
      case "BLACK_WIN" -> GameOutcome.BLACK_WIN;
      case "DRAW", "RESIGNATION" -> GameOutcome.DRAW;
      default -> GameOutcome.ONGOING;
    };
  }

  private boolean hasInProgressMatches() {
    for (MatchState state : matchStateStore.list()) {
      if (state == null) {
        continue;
      }
      MatchStateStatus status = state.getStatus();
      if (status == MatchStateStatus.ACTIVE || status == MatchStateStatus.INVITED || status == MatchStateStatus.COMPLETING) {
        return true;
      }
      String ucwStatus = state.getUcwStatus();
      if ("ACTIVE".equalsIgnoreCase(ucwStatus)) {
        return true;
      }
    }
    return false;
  }

  private static ReasoningEffort normalizeEffort(ReasoningEffort effort) {
    return effort == null ? ReasoningEffort.MEDIUM : effort;
  }
}
