package com.cooperate.chessplayer.ui;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.GameOutcome;
import com.cooperate.chessplayer.model.MatchState;
import com.cooperate.chessplayer.model.MatchStateStatus;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.cooperate.chessplayer.service.ChessEngineService;
import com.cooperate.chessplayer.service.ChessMatchOrchestrator;
import com.cooperate.chessplayer.service.MatchUpdateBroadcaster;
import com.cooperate.chessplayer.ui.component.ChessgroundBoard;
import com.github.bhlangonijr.chesslib.Board;
import com.github.bhlangonijr.chesslib.Piece;
import com.github.bhlangonijr.chesslib.PieceType;
import com.github.bhlangonijr.chesslib.Side;
import com.github.bhlangonijr.chesslib.Square;
import com.github.bhlangonijr.chesslib.move.Move;
import com.github.bhlangonijr.chesslib.move.MoveConversionException;
import com.github.bhlangonijr.chesslib.move.MoveList;
import com.vaadin.flow.component.AttachEvent;
import com.vaadin.flow.component.DetachEvent;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.combobox.ComboBox;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.H4;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.notification.Notification;
import com.vaadin.flow.component.notification.NotificationVariant;
import com.vaadin.flow.component.orderedlayout.FlexComponent;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.router.RouteAlias;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

@Route("chess")
@RouteAlias("")
@PageTitle("AI Chess Player")
public class ChessView extends Div {
  private final ChessMatchOrchestrator orchestrator;
  private final ChessEngineService chessEngineService;
  private final MatchUpdateBroadcaster updateBroadcaster;
  private final ChessPlayerProperties properties;

  private final H3 localEntityTitle = new H3();
  private final Grid<MoveRow> moveGrid = new Grid<>(MoveRow.class, false);
  private final ChessgroundBoard board = new ChessgroundBoard();
  private final Paragraph status = new Paragraph();
  private final H4 players = new H4();
  private final HorizontalLayout topBoardPlayer = new HorizontalLayout();
  private final HorizontalLayout bottomBoardPlayer = new HorizontalLayout();
  private final Div topTurnDot = new Div();
  private final Div bottomTurnDot = new Div();
  private final Span topBoardPlayerName = new Span();
  private final Span bottomBoardPlayerName = new Span();
  private final H4 topCapturedLabel = new H4();
  private final H4 bottomCapturedLabel = new H4();
  private final Paragraph topCapturedPieces = new Paragraph();
  private final Paragraph bottomCapturedPieces = new Paragraph();
  private final ComboBox<String> reasoningEffort = new ComboBox<>("Reasoning effort");
  private final Button startButton = new Button("Start game!");
  private final Button playAgainButton = new Button("Play again?");

  private UUID trackedUcwId;
  private String lastRenderedFen;
  private ChessColor lastRenderedOrientation;
  private String lastRenderedLocalMove;
  private String lastRenderedRemoteMove;
  private String lastRenderedLocalEntityText;
  private String lastRenderedPlayersText;
  private String lastRenderedStatusText;
  private String lastRenderedTopBoardPlayerText;
  private String lastRenderedBottomBoardPlayerText;
  private Boolean lastRenderedTopTurnActive;
  private Boolean lastRenderedBottomTurnActive;
  private String lastRenderedTopCapturedText;
  private String lastRenderedBottomCapturedText;
  private List<String> lastRenderedHistory = List.of();
  private boolean suppressReasoningListener;
  private Runnable unregisterUpdates;

  public ChessView(
      ChessMatchOrchestrator orchestrator,
      ChessEngineService chessEngineService,
      MatchUpdateBroadcaster updateBroadcaster,
      ChessPlayerProperties properties
  ) {
    this.orchestrator = orchestrator;
    this.chessEngineService = chessEngineService;
    this.updateBroadcaster = updateBroadcaster;
    this.properties = properties;
    buildLayout();
    refreshView();
  }

  @Override
  protected void onAttach(AttachEvent attachEvent) {
    if (unregisterUpdates == null) {
      unregisterUpdates = updateBroadcaster.register(ignored -> {
        if (getUI().isPresent()) {
          getUI().get().access(this::refreshView);
        }
      });
    }
    refreshView();
  }

  @Override
  protected void onDetach(DetachEvent detachEvent) {
    if (unregisterUpdates != null) {
      unregisterUpdates.run();
      unregisterUpdates = null;
    }
  }

  private void buildLayout() {
    setSizeFull();
    getStyle().set("padding", "1rem");

    localEntityTitle.getStyle().set("marginTop", "0");
    localEntityTitle.getStyle().set("marginBottom", "0.05rem");
    players.getStyle().set("margin", "0 0 0.05rem 0");
    status.getStyle().set("margin", "0");

    moveGrid.addColumn(MoveRow::moveNumber).setHeader(headerCell("#")).setAutoWidth(true).setFlexGrow(0);
    moveGrid.addColumn(MoveRow::white).setHeader(headerCell("White")).setFlexGrow(1);
    moveGrid.addComponentColumn(row -> blackMoveCell(row.black())).setHeader(blackHeaderCell("Black")).setFlexGrow(1);
    moveGrid.setHeight("680px");
    moveGrid.setWidth("100%");

    VerticalLayout leftPanel = new VerticalLayout();
    leftPanel.setPadding(false);
    leftPanel.setSpacing(false);
    leftPanel.setWidth("34%");
    leftPanel.setMaxWidth("440px");
    Div tableTopSpacer = new Div();
    tableTopSpacer.getStyle().set("height", "2.6rem");
    leftPanel.add(tableTopSpacer, moveGrid);

    board.getElement().getStyle().set("width", "100%");
    board.getElement().getStyle().set("height", "100%");
    board.setReducedMotionMode(properties.getReducedMotion());
    configureBoardPlayerRow(topBoardPlayer, topTurnDot, topBoardPlayerName);
    configureBoardPlayerRow(bottomBoardPlayer, bottomTurnDot, bottomBoardPlayerName);
    topBoardPlayer.getStyle().set("marginBottom", "0.2rem");
    bottomBoardPlayer.getStyle().set("marginTop", "0.2rem");
    Div boardFrame = new Div(board);
    boardFrame.getStyle().set("position", "relative");
    boardFrame.getStyle().set("width", "100%");
    boardFrame.getStyle().set("height", "680px");
    boardFrame.getStyle().set("maxWidth", "680px");

    topCapturedLabel.getStyle().set("margin", "0");
    bottomCapturedLabel.getStyle().set("margin", "0");
    topCapturedPieces.getStyle().set("margin", "0.25rem 0 0 0");
    bottomCapturedPieces.getStyle().set("margin", "0.25rem 0 0 0");
    topCapturedPieces.getStyle().set("fontSize", "1.5rem");
    bottomCapturedPieces.getStyle().set("fontSize", "1.5rem");
    topCapturedPieces.getStyle().set("lineHeight", "1.4");
    bottomCapturedPieces.getStyle().set("lineHeight", "1.4");
    topCapturedPieces.getStyle().set("letterSpacing", "0.04rem");
    bottomCapturedPieces.getStyle().set("letterSpacing", "0.04rem");

    Div topCapturedBox = new Div(topCapturedLabel, topCapturedPieces);
    Div bottomCapturedBox = new Div(bottomCapturedLabel, bottomCapturedPieces);
    topCapturedBox.getStyle().set("minHeight", "84px");
    bottomCapturedBox.getStyle().set("minHeight", "84px");

    Div capturesColumn = new Div(topCapturedBox, bottomCapturedBox);
    capturesColumn.getStyle().set("display", "flex");
    capturesColumn.getStyle().set("flexDirection", "column");
    capturesColumn.getStyle().set("justifyContent", "space-between");
    capturesColumn.getStyle().set("height", "680px");
    capturesColumn.getStyle().set("minWidth", "170px");
    capturesColumn.getStyle().set("maxWidth", "220px");
    capturesColumn.getStyle().set("paddingLeft", "0.5rem");

    reasoningEffort.setItems("low", "medium", "high");
    reasoningEffort.setAllowCustomValue(false);
    reasoningEffort.setWidth("220px");
    reasoningEffort.setValue(orchestrator.getNextReasoningEffort().apiValue());
    reasoningEffort.addValueChangeListener(event -> {
      if (suppressReasoningListener) {
        return;
      }
      applyReasoningEffortSelection(event.getValue());
    });

    startButton.addThemeVariants(ButtonVariant.LUMO_PRIMARY);
    playAgainButton.addThemeVariants(ButtonVariant.LUMO_PRIMARY);
    startButton.addClickListener(e -> startMatch());
    playAgainButton.addClickListener(e -> startMatch());

    HorizontalLayout buttonRow = new HorizontalLayout(startButton, playAgainButton);
    buttonRow.setPadding(false);
    buttonRow.setSpacing(true);
    buttonRow.setWidth("100%");
    buttonRow.setJustifyContentMode(FlexComponent.JustifyContentMode.CENTER);

    VerticalLayout controlsPanel = new VerticalLayout(reasoningEffort, buttonRow);
    controlsPanel.setPadding(false);
    controlsPanel.setSpacing(true);
    controlsPanel.setWidth("100%");
    controlsPanel.setMaxWidth("680px");
    controlsPanel.setAlignItems(FlexComponent.Alignment.CENTER);
    controlsPanel.getStyle().set("paddingTop", "0.9rem");
    controlsPanel.getStyle().set("paddingBottom", "1.4rem");

    VerticalLayout boardPanel = new VerticalLayout(topBoardPlayer, boardFrame, bottomBoardPlayer, controlsPanel);
    boardPanel.setPadding(false);
    boardPanel.setSpacing(false);
    boardPanel.setWidth("100%");
    boardPanel.setMaxWidth("680px");
    boardPanel.setAlignItems(FlexComponent.Alignment.CENTER);
    boardPanel.setJustifyContentMode(FlexComponent.JustifyContentMode.START);

    HorizontalLayout boardArea = new HorizontalLayout(boardPanel, capturesColumn);
    boardArea.setPadding(false);
    boardArea.setSpacing(true);
    boardArea.setAlignItems(FlexComponent.Alignment.START);
    boardArea.setWidthFull();
    boardArea.setFlexGrow(1, boardPanel);

    VerticalLayout rightPanel = new VerticalLayout();
    rightPanel.setPadding(false);
    rightPanel.setSpacing(false);
    rightPanel.setWidth("66%");
    rightPanel.setAlignItems(FlexComponent.Alignment.START);
    rightPanel.add(boardArea);

    VerticalLayout infoPanel = new VerticalLayout(localEntityTitle, players, status);
    infoPanel.setPadding(false);
    infoPanel.setSpacing(false);
    infoPanel.setWidthFull();
    infoPanel.setAlignItems(FlexComponent.Alignment.START);
    infoPanel.getStyle().set("paddingBottom", "0.6rem");

    HorizontalLayout content = new HorizontalLayout(leftPanel, rightPanel);
    content.setWidthFull();
    content.setHeight("calc(100% - 7rem)");
    content.setPadding(false);
    content.setSpacing(true);
    content.setAlignItems(FlexComponent.Alignment.START);
    content.setFlexGrow(1, rightPanel);
    content.setFlexGrow(0, leftPanel);

    VerticalLayout page = new VerticalLayout(infoPanel, content);
    page.setSizeFull();
    page.setPadding(false);
    page.setSpacing(false);

    add(page);
  }

  private void startMatch() {
    try {
      ReasoningEffort selectedEffort = selectedReasoningEffort();
      orchestrator.setNextReasoningEffort(selectedEffort);
      MatchState state = orchestrator.startMatch(selectedEffort);
      trackedUcwId = state.getUcwId();
      refreshView();
      Notification.show("Game started", 1800, Notification.Position.TOP_CENTER);
    } catch (Exception e) {
      Notification notification = Notification.show("Unable to start game: " + e.getMessage(), 4000, Notification.Position.TOP_CENTER);
      notification.addThemeVariants(NotificationVariant.LUMO_ERROR);
      refreshView();
    }
  }

  private void refreshView() {
    MatchState state = resolveDisplayState();
    if (state == null) {
      renderIdle();
      return;
    }
    renderMatch(state);
  }

  private MatchState resolveDisplayState() {
    List<MatchState> matches = orchestrator.listMatches();
    if (matches.isEmpty()) {
      trackedUcwId = null;
      return null;
    }

    if (trackedUcwId != null) {
      Optional<MatchState> tracked = matches.stream()
          .filter(item -> trackedUcwId.equals(item.getUcwId()))
          .findFirst();
      if (tracked.isPresent()) {
        return tracked.get();
      }
    }

    Optional<MatchState> active = matches.stream()
        .filter(this::isInProgress)
        .max(this::compareByRecentActivity);
    if (active.isPresent()) {
      trackedUcwId = active.get().getUcwId();
      return active.get();
    }

    // On a fresh UI session, do not auto-load completed history.
    // Keep startup in "new game" state unless a match is currently in progress.
    trackedUcwId = null;
    return null;
  }

  private int compareByRecentActivity(MatchState left, MatchState right) {
    return Comparator.comparing(
            (MatchState state) -> state.getUpdatedAt() != null ? state.getUpdatedAt() : Instant.EPOCH
        )
        .thenComparing(state -> state.getCreatedAt() != null ? state.getCreatedAt() : Instant.EPOCH)
        .compare(left, right);
  }

  private boolean isInProgress(MatchState state) {
    if (state == null) {
      return false;
    }
    if (state.getStatus() == MatchStateStatus.ACTIVE
        || state.getStatus() == MatchStateStatus.INVITED
        || state.getStatus() == MatchStateStatus.COMPLETING) {
      return true;
    }
    String ucwStatus = state.getUcwStatus() == null ? "" : state.getUcwStatus().toUpperCase();
    return "ACTIVE".equals(ucwStatus)
        || "FROZEN".equals(ucwStatus)
        || "COMPLETING".equals(ucwStatus)
        || "PENDING".equals(ucwStatus)
        || "INVITED_PENDING".equals(ucwStatus);
  }

  private void renderIdle() {
    String localName = toFriendlyName(properties.getLocalAgentId(), properties.getLocalDisplayName());
    String remoteName = toFriendlyName(properties.getRemoteAgentId(), properties.getRemoteDisplayName());
    ChessColor localColor = properties.getColor() == null ? ChessColor.WHITE : properties.getColor();
    String white = localColor == ChessColor.WHITE ? localName : remoteName;
    String black = localColor == ChessColor.WHITE ? remoteName : localName;
    setLocalEntityTextIfChanged("Local entity: " + localName);
    setPlayersTextIfChanged(white + " (White) vs " + black + " (Black)");
    setStatusTextIfChanged("No active game");
    setMoveHistoryIfChanged(List.of());
    updateBoardIfChanged(chessEngineService.initialFen(), localColor, null, null);
    renderCapturedPieces(
        localColor,
        white,
        black,
        CapturedPieces.empty()
    );
    renderBoardSideLabels(localColor, white, black, ChessColor.WHITE);
    setReasoningEffortValue(orchestrator.getNextReasoningEffort());
    reasoningEffort.setEnabled(true);
    startButton.setVisible(true);
    startButton.setEnabled(true);
    playAgainButton.setVisible(false);
  }

  private void renderMatch(MatchState state) {
    String localName = toFriendlyName(state.getLocalParticipantUrn(), state.getLocalUserUrn());
    String remoteName = toFriendlyName(state.getRemoteParticipantUrn(), state.getRemoteUserUrn());
    setLocalEntityTextIfChanged("Local entity: " + localName);
    ChessColor localColor = state.getLocalColor() == null ? properties.getColor() : state.getLocalColor();
    String white = localColor == ChessColor.WHITE ? localName : remoteName;
    String black = localColor == ChessColor.WHITE ? remoteName : localName;
    setPlayersTextIfChanged(white + " (White) vs " + black + " (Black)");

    String sessionIdText = state.getUcwId() == null ? "-" : state.getUcwId().toString();
    String matchStatus = state.getStatus() == null ? "UNKNOWN" : state.getStatus().name();
    String statusText = "Session: " + sessionIdText + " | Match: " + matchStatus;
    statusText = statusText + " | Effort: " + toUiEffort(state.getReasoningEffort());
    if (state.getOutcome() != null && state.getOutcome() != GameOutcome.ONGOING) {
      statusText = statusText + " | Result: " + state.getOutcome().name();
    }
    setStatusTextIfChanged(statusText);

    List<String> history = state.getMoveHistoryUci() == null ? List.of() : state.getMoveHistoryUci();
    HighlightMoves highlightMoves = resolveHighlightMoves(history, localColor);

    ChessColor orientation = state.getLocalColor() == null ? properties.getColor() : state.getLocalColor();
    String fen = state.getCurrentFen() == null || state.getCurrentFen().isBlank()
        ? chessEngineService.initialFen()
        : state.getCurrentFen();
    updateBoardIfChanged(fen, orientation, highlightMoves.localMoveUci(), highlightMoves.remoteMoveUci());
    renderBoardSideLabels(orientation, white, black, sideToMoveFromFen(fen));
    CapturedPieces capturedPieces = computeCapturedPieces(history);
    renderCapturedPieces(orientation, white, black, capturedPieces);

    setMoveHistoryIfChanged(history);

    boolean inProgress = isInProgress(state) || state.getOutcome() == GameOutcome.ONGOING;
    setReasoningEffortValue(inProgress ? state.getReasoningEffort() : orchestrator.getNextReasoningEffort());
    reasoningEffort.setEnabled(!inProgress);
    startButton.setVisible(!inProgress && state.getStatus() != MatchStateStatus.COMPLETED);
    playAgainButton.setVisible(!inProgress && state.getStatus() == MatchStateStatus.COMPLETED);
  }

  private void applyReasoningEffortSelection(String selectedValue) {
    try {
      orchestrator.setNextReasoningEffort(ReasoningEffort.fromValue(selectedValue));
    } catch (Exception e) {
      Notification notification = Notification.show("Unable to change effort: " + e.getMessage(), 3000, Notification.Position.TOP_CENTER);
      notification.addThemeVariants(NotificationVariant.LUMO_ERROR);
      setReasoningEffortValue(orchestrator.getNextReasoningEffort());
    }
  }

  private ReasoningEffort selectedReasoningEffort() {
    return ReasoningEffort.fromValue(reasoningEffort.getValue());
  }

  private void setReasoningEffortValue(ReasoningEffort effort) {
    String nextValue = toUiEffort(effort);
    if (nextValue.equals(reasoningEffort.getValue())) {
      return;
    }
    suppressReasoningListener = true;
    try {
      reasoningEffort.setValue(nextValue);
    } finally {
      suppressReasoningListener = false;
    }
  }

  private static String toUiEffort(ReasoningEffort effort) {
    ReasoningEffort normalized = effort == null ? ReasoningEffort.MEDIUM : effort;
    return normalized.name().toLowerCase(Locale.ROOT);
  }

  private void setLocalEntityTextIfChanged(String value) {
    if (Objects.equals(lastRenderedLocalEntityText, value)) {
      return;
    }
    localEntityTitle.setText(value);
    lastRenderedLocalEntityText = value;
  }

  private void setPlayersTextIfChanged(String value) {
    if (Objects.equals(lastRenderedPlayersText, value)) {
      return;
    }
    players.setText(value);
    lastRenderedPlayersText = value;
  }

  private void setStatusTextIfChanged(String value) {
    if (Objects.equals(lastRenderedStatusText, value)) {
      return;
    }
    status.setText(value);
    lastRenderedStatusText = value;
  }

  private void renderBoardSideLabels(
      ChessColor localOrientation,
      String whiteName,
      String blackName,
      ChessColor sideToMove
  ) {
    boolean localBottomIsWhite = localOrientation != ChessColor.BLACK;
    String topName = localBottomIsWhite ? blackName : whiteName;
    String bottomName = localBottomIsWhite ? whiteName : blackName;
    ChessColor topColor = localBottomIsWhite ? ChessColor.BLACK : ChessColor.WHITE;
    ChessColor bottomColor = localBottomIsWhite ? ChessColor.WHITE : ChessColor.BLACK;

    if (!Objects.equals(lastRenderedTopBoardPlayerText, topName)) {
      topBoardPlayerName.setText(topName);
      lastRenderedTopBoardPlayerText = topName;
    }
    if (!Objects.equals(lastRenderedBottomBoardPlayerText, bottomName)) {
      bottomBoardPlayerName.setText(bottomName);
      lastRenderedBottomBoardPlayerText = bottomName;
    }

    boolean topTurnActive = sideToMove == topColor;
    if (!Objects.equals(lastRenderedTopTurnActive, topTurnActive)) {
      topTurnDot.getStyle().set("visibility", topTurnActive ? "visible" : "hidden");
      lastRenderedTopTurnActive = topTurnActive;
    }
    boolean bottomTurnActive = sideToMove == bottomColor;
    if (!Objects.equals(lastRenderedBottomTurnActive, bottomTurnActive)) {
      bottomTurnDot.getStyle().set("visibility", bottomTurnActive ? "visible" : "hidden");
      lastRenderedBottomTurnActive = bottomTurnActive;
    }
  }

  private void setMoveHistoryIfChanged(List<String> history) {
    List<String> safeHistory = history == null ? List.of() : List.copyOf(history);
    if (lastRenderedHistory.equals(safeHistory)) {
      return;
    }
    moveGrid.setItems(buildMoveRows(safeHistory));
    if (!safeHistory.isEmpty()) {
      int lastRowIndex = (safeHistory.size() - 1) / 2;
      scrollMoveGridToLatest(lastRowIndex);
    }
    lastRenderedHistory = safeHistory;
  }

  private void updateBoardIfChanged(String fen, ChessColor orientation, String localLastMoveUci, String remoteLastMoveUci) {
    if (Objects.equals(lastRenderedFen, fen)
        && lastRenderedOrientation == orientation
        && Objects.equals(lastRenderedLocalMove, localLastMoveUci)
        && Objects.equals(lastRenderedRemoteMove, remoteLastMoveUci)) {
      return;
    }
    board.setPosition(fen, orientation, localLastMoveUci, remoteLastMoveUci);
    lastRenderedFen = fen;
    lastRenderedOrientation = orientation;
    lastRenderedLocalMove = localLastMoveUci;
    lastRenderedRemoteMove = remoteLastMoveUci;
  }

  private void renderCapturedPieces(
      ChessColor localOrientation,
      String whiteName,
      String blackName,
      CapturedPieces capturedPieces
  ) {
    boolean localBottomIsWhite = localOrientation != ChessColor.BLACK;
    String topName = localBottomIsWhite ? blackName : whiteName;
    String bottomName = localBottomIsWhite ? whiteName : blackName;
    List<String> topCaptured = localBottomIsWhite ? capturedPieces.byBlack : capturedPieces.byWhite;
    List<String> bottomCaptured = localBottomIsWhite ? capturedPieces.byWhite : capturedPieces.byBlack;

    topCapturedLabel.setText(topName + " captured");
    bottomCapturedLabel.setText(bottomName + " captured");
    String topText = formatCaptured(topCaptured);
    String bottomText = formatCaptured(bottomCaptured);
    if (!Objects.equals(lastRenderedTopCapturedText, topText)) {
      topCapturedPieces.setText(topText);
      lastRenderedTopCapturedText = topText;
    }
    if (!Objects.equals(lastRenderedBottomCapturedText, bottomText)) {
      bottomCapturedPieces.setText(bottomText);
      lastRenderedBottomCapturedText = bottomText;
    }
  }

  private CapturedPieces computeCapturedPieces(List<String> history) {
    if (history == null || history.isEmpty()) {
      return CapturedPieces.empty();
    }
    Board replay = chessEngineService.loadBoard(chessEngineService.initialFen());
    List<String> capturedByWhite = new ArrayList<>();
    List<String> capturedByBlack = new ArrayList<>();

    for (String uci : history) {
      if (uci == null || uci.length() < 4) {
        break;
      }
      Move move = parseMove(uci, replay.getSideToMove());
      if (move == null) {
        break;
      }

      Piece captured = replay.getPiece(move.getTo());
      if (captured != null && captured != Piece.NONE && captured.getPieceType() != PieceType.KING) {
        String glyph = glyphForCapturedPiece(captured);
        if (!glyph.isEmpty()) {
          if (replay.getSideToMove() == Side.WHITE) {
            capturedByWhite.add(glyph);
          } else {
            capturedByBlack.add(glyph);
          }
        }
      }

      if (!replay.doMove(move)) {
        break;
      }
    }
    return new CapturedPieces(capturedByWhite, capturedByBlack);
  }

  private Move parseMove(String uci, Side sideToMove) {
    try {
      String fromToken = uci.substring(0, 2).toUpperCase(Locale.ROOT);
      String toToken = uci.substring(2, 4).toUpperCase(Locale.ROOT);
      Square from = Square.fromValue(fromToken);
      Square to = Square.fromValue(toToken);
      if (from == null || to == null || from == Square.NONE || to == Square.NONE) {
        return null;
      }
      if (uci.length() >= 5) {
        Piece promotion = parsePromotionPiece(uci.charAt(4), sideToMove);
        if (promotion == Piece.NONE) {
          return null;
        }
        return new Move(from, to, promotion);
      }
      return new Move(from, to);
    } catch (RuntimeException e) {
      return null;
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

  private static String glyphForCapturedPiece(Piece captured) {
    if (captured == null || captured == Piece.NONE) {
      return "";
    }
    return switch (captured) {
      case WHITE_QUEEN -> "♕";
      case WHITE_ROOK -> "♖";
      case WHITE_BISHOP -> "♗";
      case WHITE_KNIGHT -> "♘";
      case WHITE_PAWN -> "♙";
      case BLACK_QUEEN -> "♛";
      case BLACK_ROOK -> "♜";
      case BLACK_BISHOP -> "♝";
      case BLACK_KNIGHT -> "♞";
      case BLACK_PAWN -> "♟";
      default -> "";
    };
  }

  private static String formatCaptured(List<String> captured) {
    if (captured == null || captured.isEmpty()) {
      return "-";
    }
    return String.join(" ", captured);
  }

  private static Div headerCell(String text) {
    Div cell = new Div();
    cell.setText(text);
    cell.getStyle().set("fontWeight", "700");
    return cell;
  }

  private static Div blackHeaderCell(String text) {
    Div cell = headerCell(text);
    cell.getStyle().set("backgroundColor", "#111111");
    cell.getStyle().set("color", "#ffffff");
    cell.getStyle().set("padding", "0.35rem 0.5rem");
    cell.getStyle().set("borderRadius", "4px");
    cell.getStyle().set("textAlign", "center");
    return cell;
  }

  private static Div blackMoveCell(String move) {
    Div cell = new Div();
    cell.setText(move == null ? "" : move);
    cell.getStyle().set("backgroundColor", "#111111");
    cell.getStyle().set("color", "#ffffff");
    cell.getStyle().set("fontWeight", "600");
    cell.getStyle().set("padding", "0.25rem 0.35rem");
    cell.getStyle().set("borderRadius", "4px");
    cell.setWidthFull();
    return cell;
  }

  private void configureBoardPlayerRow(HorizontalLayout row, Div turnDot, Span name) {
    row.setPadding(false);
    row.setSpacing(false);
    row.setWidth("100%");
    row.setMaxWidth("680px");
    row.getStyle().set("height", "2.4rem");
    row.setAlignItems(FlexComponent.Alignment.CENTER);
    row.setJustifyContentMode(FlexComponent.JustifyContentMode.CENTER);
    row.getStyle().set("pointerEvents", "none");

    turnDot.getStyle().set("width", "1.2rem");
    turnDot.getStyle().set("height", "1.2rem");
    turnDot.getStyle().set("borderRadius", "50%");
    turnDot.getStyle().set("marginRight", "0.55rem");
    turnDot.getStyle().set("backgroundColor", "#1d4ed8");
    turnDot.getStyle().set("boxShadow", "0 0 0 2px rgba(255,255,255,0.75)");
    turnDot.getStyle().set("visibility", "hidden");

    name.getStyle().set("fontSize", "1.35rem");
    name.getStyle().set("fontWeight", "800");
    name.getStyle().set("lineHeight", "1.2");
    name.getStyle().set("color", "#111827");
    name.getStyle().set("textShadow", "0 0 2px rgba(255,255,255,0.55)");

    Div badge = new Div(turnDot, name);
    badge.getStyle().set("display", "inline-flex");
    badge.getStyle().set("alignItems", "center");
    badge.getStyle().set("justifyContent", "center");
    badge.getStyle().set("backgroundColor", "rgba(255,255,255,0.78)");
    badge.getStyle().set("padding", "0.22rem 0.65rem");
    badge.getStyle().set("borderRadius", "999px");
    badge.getStyle().set("border", "2px solid #111111");
    badge.getStyle().set("boxShadow", "0 1px 2px rgba(0,0,0,0.22)");

    row.removeAll();
    row.add(badge);
  }

  private void scrollMoveGridToLatest(int lastRowIndex) {
    moveGrid.getElement().executeJs(
        "requestAnimationFrame(() => {"
            + "if (typeof this.scrollToIndex === 'function') { this.scrollToIndex($0); }"
            + "const table = this.shadowRoot && this.shadowRoot.querySelector('#table');"
            + "if (table) { table.scrollTop = table.scrollHeight; }"
            + "});",
        Math.max(0, lastRowIndex)
    );
  }

  private static HighlightMoves resolveHighlightMoves(List<String> history, ChessColor localColor) {
    if (history == null || history.isEmpty()) {
      return HighlightMoves.empty();
    }
    ChessColor normalizedLocal = localColor == null ? ChessColor.WHITE : localColor;
    for (int index = history.size() - 1; index >= 0; index--) {
      String move = history.get(index);
      if (move == null || move.length() < 4) {
        continue;
      }
      ChessColor moveSide = (index % 2 == 0) ? ChessColor.WHITE : ChessColor.BLACK;
      if (moveSide == normalizedLocal) {
        return new HighlightMoves(move, null);
      }
      return new HighlightMoves(null, move);
    }
    return HighlightMoves.empty();
  }

  private ChessColor sideToMoveFromFen(String fen) {
    try {
      Board boardState = chessEngineService.loadBoard(fen);
      return ChessColor.fromSide(boardState.getSideToMove());
    } catch (Exception e) {
      return ChessColor.WHITE;
    }
  }

  private List<MoveRow> buildMoveRows(List<String> uciMoves) {
    if (uciMoves == null || uciMoves.isEmpty()) {
      return List.of();
    }

    List<String> sanMoves = toSanMoves(uciMoves);
    List<MoveRow> rows = new ArrayList<>();
    for (int index = 0; index < sanMoves.size(); index += 2) {
      int moveNumber = (index / 2) + 1;
      String white = sanMoves.get(index);
      String black = index + 1 < sanMoves.size() ? sanMoves.get(index + 1) : "";
      rows.add(new MoveRow(moveNumber, white, black));
    }
    return rows;
  }

  private List<String> toSanMoves(List<String> uciMoves) {
    MoveList moveList = new MoveList();
    Side side = Side.WHITE;
    try {
      for (String uciMove : uciMoves) {
        if (uciMove == null || uciMove.length() < 4) {
          throw new MoveConversionException("invalid UCI move: " + uciMove);
        }
        moveList.add(new Move(uciMove, side));
        side = side.flip();
      }
      String[] sanArray = moveList.toSanArray();
      List<String> sanMoves = new ArrayList<>(sanArray.length);
      for (String san : sanArray) {
        sanMoves.add(san);
      }
      return sanMoves;
    } catch (Exception e) {
      return new ArrayList<>(uciMoves);
    }
  }

  private String toFriendlyName(String agentId, String displayName) {
    if (displayName != null && !displayName.isBlank()) {
      return displayName;
    }
    if (agentId == null || agentId.isBlank()) {
      return "AI Player";
    }
    String normalized = agentId.trim();
    if (normalized.startsWith("agent:")) {
      normalized = normalized.substring("agent:".length());
    }
    int at = normalized.indexOf('@');
    if (at > 0) {
      normalized = normalized.substring(0, at);
    }
    return normalized.isBlank() ? "AI Player" : normalized;
  }

  private record MoveRow(int moveNumber, String white, String black) {
  }

  private record HighlightMoves(String localMoveUci, String remoteMoveUci) {
    private static HighlightMoves empty() {
      return new HighlightMoves(null, null);
    }
  }

  private record CapturedPieces(List<String> byWhite, List<String> byBlack) {
    private static CapturedPieces empty() {
      return new CapturedPieces(List.of(), List.of());
    }
  }
}
