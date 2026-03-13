package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.GameOutcome;
import com.cooperate.chessplayer.model.MatchState;
import com.cooperate.chessplayer.model.MatchStateStatus;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;

import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ChessMatchOrchestratorTest {

  @TempDir
  Path tempDir;

  @Test
  void shouldCreateAndUpdateStateFromInboundMovePayload() throws Exception {
    TestFixture fixture = createFixture(ChessColor.BLACK);

    UUID matchId = UUID.randomUUID();
    String payload = fixture.payloadCodec.toMovePayload(matchId, 1, ChessColor.BLACK, "e2e4", null);
    Map<String, Object> payloadMap = fixture.objectMapper.readValue(payload, new TypeReference<>() {
    });

    fixture.orchestrator.onInboundPayload(payloadMap);

    MatchState state = fixture.orchestrator.findMatch(matchId).orElseThrow();
    assertEquals(matchId, state.getMatchId());
    assertEquals(1, state.getLatestSequence());
    assertEquals("e2e4", state.getMoveHistoryUci().getFirst());
    assertEquals(MatchStateStatus.ACTIVE, state.getStatus());
  }

  @Test
  void shouldSendMoveWhenItIsLocalTurn() {
    TestFixture fixture = createFixture(ChessColor.WHITE);
    when(fixture.acpChessClient.sendChessEvent(any())).thenReturn(true);

    MatchState started = fixture.orchestrator.startMatch();
    fixture.orchestrator.poll();

    MatchState updated = fixture.orchestrator.findMatch(started.getUcwId()).orElseThrow();
    assertTrue(updated.getLatestSequence() >= 1);
    assertTrue(updated.getMoveHistoryUci().size() >= 1);
    assertEquals(MatchStateStatus.ACTIVE, updated.getStatus());
    verify(fixture.acpChessClient, times(1)).sendChessEvent(any());
  }

  @Test
  void shouldSendTerminalEventAndCompleteWhenGameBecomesTerminal() {
    TestFixture fixture = createFixture(ChessColor.WHITE);
    fixture.properties.setMaxPlies(0);
    when(fixture.acpChessClient.sendChessEvent(any())).thenReturn(true);

    MatchState started = fixture.orchestrator.startMatch();
    fixture.orchestrator.poll();

    MatchState updated = fixture.orchestrator.findMatch(started.getUcwId()).orElseThrow();
    assertNotNull(updated.getOutcome());
    assertEquals(GameOutcome.DRAW, updated.getOutcome());
    assertEquals(MatchStateStatus.COMPLETED, updated.getStatus());
    assertTrue(updated.isCompletionProposalSent());
    verify(fixture.acpChessClient, times(1)).sendChessEvent(any());
  }

  @Test
  void shouldRejectReasoningEffortChangeWhileMatchIsActive() {
    TestFixture fixture = createFixture(ChessColor.WHITE);
    fixture.orchestrator.startMatch();
    assertThrows(
        IllegalStateException.class,
        () -> fixture.orchestrator.setNextReasoningEffort(ReasoningEffort.HIGH)
    );
  }

  private TestFixture createFixture(ChessColor localColor) {
    ObjectMapper objectMapper = new ObjectMapper().registerModule(new JavaTimeModule());
    ChessPlayerProperties properties = new ChessPlayerProperties();
    properties.setColor(localColor);
    properties.setMoveSendDelayMs(0);
    properties.setPgnExportEnabled(false);
    properties.setStateFile(tempDir.resolve("state/matches.json").toString());
    properties.setLocalAgentId("agent:player1@localhost:8088");
    properties.setRemoteAgentId("agent:player2@localhost:8089");
    properties.setLocalDisplayName("Player 1 AI");
    properties.setRemoteDisplayName("Player 2 AI");

    AcpChessClient acpChessClient = Mockito.mock(AcpChessClient.class);
    ChessPayloadCodec payloadCodec = new ChessPayloadCodec(objectMapper);
    ChessEngineService chessEngineService = new ChessEngineService();
    MatchStateStore matchStateStore = new MatchStateStore(objectMapper, properties, new MatchUpdateBroadcaster());
    PgnExporter pgnExporter = new PgnExporter(properties);

    ChessMatchOrchestrator orchestrator = new ChessMatchOrchestrator(
        properties,
        acpChessClient,
        chessEngineService,
        payloadCodec,
        matchStateStore,
        pgnExporter
    );
    return new TestFixture(orchestrator, payloadCodec, objectMapper, acpChessClient, properties);
  }

  private record TestFixture(
      ChessMatchOrchestrator orchestrator,
      ChessPayloadCodec payloadCodec,
      ObjectMapper objectMapper,
      AcpChessClient acpChessClient,
      ChessPlayerProperties properties
  ) {
  }
}
