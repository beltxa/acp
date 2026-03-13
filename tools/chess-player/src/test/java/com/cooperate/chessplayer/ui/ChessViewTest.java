package com.cooperate.chessplayer.ui;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.MatchState;
import com.cooperate.chessplayer.model.MatchStateStatus;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.cooperate.chessplayer.service.ChessEngineService;
import com.cooperate.chessplayer.service.ChessMatchOrchestrator;
import com.cooperate.chessplayer.service.MatchUpdateBroadcaster;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.lang.reflect.Method;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.when;

class ChessViewTest {

  @Test
  void shouldHighlightOnlyMostRecentMoveForLocalPerspective() throws Exception {
    Object highlightWhenOpponentMoved = invokeResolveHighlightMoves(List.of("e2e4", "e7e5"), ChessColor.WHITE);
    assertNull(readHighlightField(highlightWhenOpponentMoved, "localMoveUci"));
    assertEquals("e7e5", readHighlightField(highlightWhenOpponentMoved, "remoteMoveUci"));

    Object highlightWhenLocalMoved = invokeResolveHighlightMoves(List.of("e2e4", "e7e5", "g1f3"), ChessColor.WHITE);
    assertEquals("g1f3", readHighlightField(highlightWhenLocalMoved, "localMoveUci"));
    assertNull(readHighlightField(highlightWhenLocalMoved, "remoteMoveUci"));
  }

  @Test
  void shouldResolveIdleWhenOnlyCompletedMatchesExist() throws Exception {
    ChessMatchOrchestrator orchestrator = Mockito.mock(ChessMatchOrchestrator.class);
    ChessEngineService engine = Mockito.mock(ChessEngineService.class);
    MatchUpdateBroadcaster broadcaster = Mockito.mock(MatchUpdateBroadcaster.class);
    ChessPlayerProperties properties = new ChessPlayerProperties();
    properties.setColor(ChessColor.WHITE);

    MatchState completed = new MatchState();
    completed.setUcwId(UUID.randomUUID());
    completed.setStatus(MatchStateStatus.COMPLETED);
    completed.setUcwStatus("COMPLETED");
    completed.setCreatedAt(Instant.now().minusSeconds(10));
    completed.setUpdatedAt(Instant.now().minusSeconds(5));

    when(orchestrator.getNextReasoningEffort()).thenReturn(ReasoningEffort.MEDIUM);
    when(orchestrator.listMatches()).thenReturn(List.of(completed));
    when(engine.initialFen()).thenReturn("startpos");
    when(broadcaster.register(Mockito.any())).thenReturn(() -> {
    });

    ChessView view = new ChessView(orchestrator, engine, broadcaster, properties);
    MatchState resolved = invokeResolveDisplayState(view);
    assertNull(resolved);
  }

  @Test
  void shouldResolveActiveMatchWhenPresent() throws Exception {
    ChessMatchOrchestrator orchestrator = Mockito.mock(ChessMatchOrchestrator.class);
    ChessEngineService engine = Mockito.mock(ChessEngineService.class);
    MatchUpdateBroadcaster broadcaster = Mockito.mock(MatchUpdateBroadcaster.class);
    ChessPlayerProperties properties = new ChessPlayerProperties();
    properties.setColor(ChessColor.WHITE);

    MatchState active = new MatchState();
    active.setUcwId(UUID.randomUUID());
    active.setStatus(MatchStateStatus.ACTIVE);
    active.setUcwStatus("ACTIVE");
    active.setCreatedAt(Instant.now().minusSeconds(20));
    active.setUpdatedAt(Instant.now().minusSeconds(1));

    when(orchestrator.getNextReasoningEffort()).thenReturn(ReasoningEffort.MEDIUM);
    when(orchestrator.listMatches()).thenReturn(List.of(active));
    when(engine.initialFen()).thenReturn("startpos");
    when(broadcaster.register(Mockito.any())).thenReturn(() -> {
    });

    ChessView view = new ChessView(orchestrator, engine, broadcaster, properties);
    MatchState resolved = invokeResolveDisplayState(view);
    assertNotNull(resolved);
    assertEquals(active.getUcwId(), resolved.getUcwId());
  }

  private static MatchState invokeResolveDisplayState(ChessView view) throws Exception {
    Method method = ChessView.class.getDeclaredMethod("resolveDisplayState");
    method.setAccessible(true);
    return (MatchState) method.invoke(view);
  }

  private static Object invokeResolveHighlightMoves(List<String> history, ChessColor localColor) throws Exception {
    Method method = ChessView.class.getDeclaredMethod("resolveHighlightMoves", List.class, ChessColor.class);
    method.setAccessible(true);
    return method.invoke(null, history, localColor);
  }

  private static String readHighlightField(Object highlightMoves, String name) throws Exception {
    Method accessor = highlightMoves.getClass().getDeclaredMethod(name);
    accessor.setAccessible(true);
    return (String) accessor.invoke(highlightMoves);
  }
}
