package com.cooperate.poker.dealer.ui;

import com.cooperate.poker.common.model.PlayerState;
import com.cooperate.poker.common.model.PlayerStatus;
import com.cooperate.poker.common.model.GameStatus;
import com.cooperate.poker.common.model.TableState;
import com.cooperate.poker.dealer.security.DealerAuthService;
import com.cooperate.poker.dealer.service.DealerService;
import com.vaadin.flow.component.AttachEvent;
import com.vaadin.flow.component.Html;
import com.vaadin.flow.component.Text;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.Image;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.textfield.TextArea;
import com.vaadin.flow.router.BeforeEnterEvent;
import com.vaadin.flow.router.BeforeEnterObserver;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

@Route("")
@PageTitle("Distributed AI Poker Dealer")
public class PokerTableView extends VerticalLayout implements BeforeEnterObserver {
  private static final int COMMUNITY_CARD_COUNT = 5;
  private static final int PLAYER_DEAL_DELAY_MS = 300;
  private static final int COMMUNITY_DEAL_DELAY_MS = 500;

  private final DealerService dealerService;
  private final DealerAuthService authService;

  private final H2 statusLabel = new H2("Status: WAITING_FOR_PLAYERS");
  private final Div handLabel = new Div(new Text("Hand: 0"));
  private final Div roundLabel = new Div(new Text("Round: PRE_FLOP"));

  private final Div board = new Div();
  private final Div potLabel = new Div();
  private final Div communityLabel = new Div(new Text("Community"));
  private final Div communityCards = new Div();

  private final List<CardSlot> communityCardSlots = new ArrayList<>(COMMUNITY_CARD_COUNT);
  private final Map<String, PlayerPanel> playerPanels = new LinkedHashMap<>();

  private final TextArea actionLog = new TextArea("Action Log");
  private final TextArea reasoningLog = new TextArea("AI Decision Log");
  private final Span authenticatedUser = new Span("-");

  public PokerTableView(DealerService dealerService, DealerAuthService authService) {
    this.dealerService = dealerService;
    this.authService = authService;

    setSizeFull();
    setPadding(true);
    setSpacing(true);

    add(new Html(buildStyles()));

    H3 title = new H3("Co-operate AI Poker Demo");

    Button startGameButton = new Button("Start Game", event -> dealerService.startGame());
    Button resetGameButton = new Button("Reset Game", event -> dealerService.resetGame());
    Button logoutButton = new Button("Logout", event -> logout());
    HorizontalLayout controls = new HorizontalLayout(startGameButton, resetGameButton);
    if (authService.isEnabled()) {
      String username = DealerSessionState.getAuthenticatedUsername();
      authenticatedUser.setText(username == null ? "Not logged in" : "Logged as " + username);
      controls.add(authenticatedUser, logoutButton);
    }

    HorizontalLayout gameInfo = new HorizontalLayout(handLabel, roundLabel);
    gameInfo.setWidthFull();

    buildBoard();

    actionLog.setReadOnly(true);
    actionLog.setWidthFull();
    actionLog.setHeight("190px");

    reasoningLog.setReadOnly(true);
    reasoningLog.setWidthFull();
    reasoningLog.setHeight("190px");

    VerticalLayout logs = new VerticalLayout(actionLog, reasoningLog);
    logs.setPadding(false);
    logs.setSpacing(true);
    logs.setWidth("30%");

    HorizontalLayout content = new HorizontalLayout(board, logs);
    content.setSizeFull();
    content.setFlexGrow(1, board);
    content.setFlexGrow(0, logs);

    add(title, controls, statusLabel, gameInfo, content);
    setFlexGrow(1, content);

    refresh();
  }

  @Override
  public void beforeEnter(BeforeEnterEvent event) {
    if (authService.isEnabled() && !DealerSessionState.isAuthenticated()) {
      event.forwardTo("login");
    }
  }

  @Override
  protected void onAttach(AttachEvent attachEvent) {
    super.onAttach(attachEvent);
    attachEvent.getUI().setPollInterval(250);
    attachEvent.getUI().addPollListener(event -> refresh());
  }

  private void buildBoard() {
    board.addClassName("poker-board");

    Div tableSurface = new Div();
    tableSurface.addClassName("table-surface");

    potLabel.addClassName("pot-label");

    communityLabel.addClassName("community-label");
    communityCards.addClassName("community-cards");
    for (int i = 0; i < COMMUNITY_CARD_COUNT; i++) {
      CardSlot slot = new CardSlot();
      slot.clear();
      communityCardSlots.add(slot);
      communityCards.add(slot.component());
    }

    playerPanels.put("Player-1", new PlayerPanel("Player-1", "left: 3%; top: 37%;", 0));
    playerPanels.put("Player-2", new PlayerPanel("Player-2", "left: 38%; top: 2%;", 2));
    playerPanels.put("Player-3", new PlayerPanel("Player-3", "right: 3%; top: 37%;", 4));
    playerPanels.put("Player-4", new PlayerPanel("Player-4", "left: 38%; bottom: 2%;", 6));

    board.add(tableSurface, potLabel, communityLabel, communityCards);
    playerPanels.values().stream().map(PlayerPanel::root).forEach(board::add);
  }

  private void refresh() {
    TableState state = dealerService.getCurrentTableState();
    if (state == null) {
      return;
    }

    statusLabel.setText("Status: " + state.status());
    handLabel.setText("Hand: " + state.gameState().handNumber());
    roundLabel.setText("Round: " + state.gameState().roundType());
    potLabel.setText("Pot: $" + state.gameState().potSize());

    updateCommunityCards(state);

    for (Map.Entry<String, PlayerPanel> entry : playerPanels.entrySet()) {
      String playerId = entry.getKey();
      PlayerPanel panel = entry.getValue();
      PlayerState player = state.gameState().playerStates().get(playerId);
      boolean isCurrentPlayer = Objects.equals(playerId, state.gameState().currentPlayer());

      if (player == null) {
        panel.showWaiting();
      } else {
        panel.update(player, isCurrentPlayer);
      }
    }

    actionLog.setValue(String.join("\n", state.actionLog()));
    reasoningLog.setValue(String.join("\n", state.reasoningLog()));
  }

  private void updateCommunityCards(TableState state) {
    List<String> cards = state.gameState().communityCards();
    boolean showFaceDown = state.gameState().handNumber() > 0
        && state.status() != GameStatus.WAITING_FOR_PLAYERS
        && state.status() != GameStatus.INVITING_PLAYERS;

    for (int i = 0; i < communityCardSlots.size(); i++) {
      CardSlot slot = communityCardSlots.get(i);
      String card = i < cards.size() ? cards.get(i) : null;
      if (card == null) {
        if (showFaceDown) {
          slot.showFaceDown(i, COMMUNITY_DEAL_DELAY_MS);
        } else {
          slot.clear();
        }
      } else {
        int revealDelayIndex = cards.size() <= 3 ? i : 0;
        slot.showCard(card, true, revealDelayIndex, COMMUNITY_DEAL_DELAY_MS);
      }
    }
  }

  private static String buildStyles() {
    return """
        <style>
          .poker-board {
            position: relative;
            width: 70%;
            min-height: 620px;
            border: 1px solid rgba(255,255,255,0.22);
            border-radius: 16px;
            overflow: hidden;
            background-image:
              linear-gradient(0deg, rgba(6, 25, 11, 0.45), rgba(6, 25, 11, 0.45)),
              url('/assets/table/poker-table-top.png');
            background-size: cover;
            background-position: center;
            box-shadow: 0 16px 32px rgba(0,0,0,0.28);
          }

          .table-surface {
            position: absolute;
            left: 50%;
            top: 50%;
            width: 68%;
            height: 58%;
            transform: translate(-50%, -50%);
            border-radius: 50%;
            border: 6px solid #4b2f13;
            background: radial-gradient(circle at 50% 35%, #1e9b57 0%, #0f7a3d 70%, #095d2f 100%);
            box-shadow: inset 0 0 32px rgba(0,0,0,0.25);
          }

          .pot-label {
            position: absolute;
            left: 50%;
            top: 42%;
            transform: translate(-50%, -50%);
            color: #fff;
            font-weight: 700;
            font-size: 16px;
            background: rgba(8, 15, 12, 0.6);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 10px;
            padding: 8px 14px;
            z-index: 6;
          }

          .community-label {
            position: absolute;
            left: 50%;
            top: 48%;
            transform: translate(-50%, -50%);
            color: #f5f7f8;
            font-size: 12px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            z-index: 6;
          }

          .community-cards {
            position: absolute;
            left: 50%;
            top: 54%;
            transform: translate(-50%, -50%);
            display: flex;
            gap: 10px;
            z-index: 6;
          }

          .player-panel {
            position: absolute;
            width: 230px;
            min-height: 165px;
            background: rgba(252, 252, 252, 0.96);
            border: 2px solid #243b2f;
            border-radius: 12px;
            padding: 8px 10px;
            box-shadow: 0 8px 18px rgba(0,0,0,0.28);
            display: flex;
            flex-direction: column;
            gap: 6px;
            z-index: 10;
            transition: border-color 0.2s ease, opacity 0.2s ease;
          }

          .player-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
          }

          .player-name {
            font-weight: 700;
            color: #19261d;
          }

          .player-status {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.03em;
            color: #355247;
            text-transform: uppercase;
          }

          .player-stats {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            font-size: 12px;
            color: #1d2f26;
          }

          .player-last-action {
            font-size: 12px;
            color: #2c4235;
            min-height: 16px;
          }

          .player-cards {
            display: flex;
            gap: 8px;
          }

          .active-turn {
            border-color: #d62828;
            box-shadow: 0 0 0 3px rgba(214,40,40,0.2), 0 8px 18px rgba(0,0,0,0.28);
          }

          .delta-win {
            color: #0a7e42;
            font-weight: 700;
          }

          .delta-loss {
            color: #b11b1b;
            font-weight: 700;
          }

          .delta-flat {
            color: #2b3f34;
            font-weight: 700;
          }

          .poker-card-slot {
            width: 58px;
            height: 84px;
            perspective: 900px;
            transform-style: preserve-3d;
            --deal-delay: 0s;
          }

          .poker-card-inner {
            width: 100%;
            height: 100%;
            position: relative;
            transform-style: preserve-3d;
            transition: transform 360ms ease;
          }

          .poker-card-slot.is-face-up .poker-card-inner {
            transform: rotateY(180deg);
          }

          .poker-card-face {
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 8px;
            backface-visibility: hidden;
            object-fit: cover;
            box-shadow: 0 4px 8px rgba(0,0,0,0.22);
          }

          .poker-card-front {
            transform: rotateY(180deg);
          }

          .poker-card-slot.is-empty {
            opacity: 0.28;
          }

          .poker-card-slot.dealt {
            animation: deal-in 360ms cubic-bezier(.2,.8,.2,1) both;
            animation-delay: var(--deal-delay);
          }

          @keyframes deal-in {
            from {
              transform: translateY(32px) scale(0.84);
              opacity: 0;
            }
            to {
              transform: translateY(0) scale(1);
              opacity: 1;
            }
          }

          @media (max-width: 1250px) {
            .poker-board {
              width: 100%;
              min-height: 660px;
            }

            .player-panel {
              width: 210px;
            }
          }

          @media (max-width: 920px) {
            .poker-board {
              min-height: 760px;
            }

            .player-panel {
              width: 46%;
              min-height: 154px;
            }
          }
        </style>
        """;
  }

  private void logout() {
    DealerSessionState.clear();
    getUI().ifPresent(ui -> ui.navigate("login"));
  }

  private static String formatDelta(int amount) {
    if (amount > 0) {
      return "+$" + amount;
    }
    if (amount < 0) {
      return "-$" + Math.abs(amount);
    }
    return "$0";
  }

  private static String cardPath(String cardCode) {
    if (cardCode == null || cardCode.length() != 2) {
      return "/assets/cards/back.svg";
    }
    String rank = cardCode.substring(0, 1).toUpperCase(Locale.ROOT);
    if ("T".equals(rank)) {
      rank = "10";
    }
    String suit = cardCode.substring(1, 2).toLowerCase(Locale.ROOT);
    return "/assets/cards/" + rank + suit + ".svg";
  }

  private final class PlayerPanel {
    private final Div root = new Div();
    private final Span status = new Span();
    private final Span stack = new Span();
    private final Span handDelta = new Span();
    private final Span totalDelta = new Span();
    private final Span lastAction = new Span();
    private final List<CardSlot> cardSlots = List.of(new CardSlot(), new CardSlot());
    private final int baseDealIndex;

    private PlayerPanel(String playerId, String positionStyle, int baseDealIndex) {
      this.baseDealIndex = baseDealIndex;
      root.addClassName("player-panel");

      Div header = new Div();
      header.addClassName("player-header");
      Span name = new Span(playerId);
      name.addClassName("player-name");
      status.addClassName("player-status");
      header.add(name, status);

      Div stats = new Div();
      stats.addClassName("player-stats");
      stack.setText("Stack: $0");
      handDelta.setText("Hand: $0");
      totalDelta.setText("Net: $0");
      stats.add(stack, handDelta, totalDelta);

      lastAction.addClassName("player-last-action");

      Div cards = new Div();
      cards.addClassName("player-cards");
      cardSlots.stream().map(CardSlot::component).forEach(cards::add);

      root.add(header, stats, lastAction, cards);

      for (String assignment : positionStyle.split(";")) {
        String trimmed = assignment.trim();
        if (trimmed.isBlank()) {
          continue;
        }
        String[] pair = trimmed.split(":", 2);
        root.getStyle().set(pair[0].trim(), pair[1].trim());
      }
    }

    private Div root() {
      return root;
    }

    private void showWaiting() {
      status.setText("WAITING");
      stack.setText("Stack: --");
      handDelta.setText("Hand: --");
      totalDelta.setText("Net: --");
      lastAction.setText("Last: waiting for player...");
      handDelta.removeClassNames("delta-win", "delta-loss", "delta-flat");
      totalDelta.removeClassNames("delta-win", "delta-loss", "delta-flat");
      root.removeClassName("active-turn");
      root.getStyle().set("opacity", "0.65");
      cardSlots.forEach(CardSlot::clear);
    }

    private void update(PlayerState player, boolean isCurrentPlayer) {
      status.setText(player.status().name());
      stack.setText("Stack: $" + player.stack());
      handDelta.setText("Hand: " + formatDelta(player.handDelta()));
      totalDelta.setText("Net: " + formatDelta(player.totalDelta()));
      applyDeltaClass(handDelta, player.handDelta());
      applyDeltaClass(totalDelta, player.totalDelta());

      String actionText = "-";
      if (player.lastAction() != null) {
        actionText = player.lastAction().action().name();
        if (player.lastAction().amount() > 0) {
          actionText += " $" + player.lastAction().amount();
        }
      }
      lastAction.setText("Last: " + actionText);

      if (isCurrentPlayer) {
        root.addClassName("active-turn");
      } else {
        root.removeClassName("active-turn");
      }

      boolean dimmed = player.status() == PlayerStatus.FOLDED || player.status() == PlayerStatus.ELIMINATED;
      root.getStyle().set("opacity", dimmed ? "0.58" : "1");

      for (int i = 0; i < cardSlots.size(); i++) {
        CardSlot slot = cardSlots.get(i);
        String card = i < player.holeCards().size() ? player.holeCards().get(i) : null;
        if (card == null) {
          slot.clear();
        } else {
          slot.showCard(card, true, baseDealIndex + i, PLAYER_DEAL_DELAY_MS);
        }
      }
    }

    private void applyDeltaClass(Span target, int amount) {
      target.removeClassNames("delta-win", "delta-loss", "delta-flat");
      if (amount > 0) {
        target.addClassName("delta-win");
      } else if (amount < 0) {
        target.addClassName("delta-loss");
      } else {
        target.addClassName("delta-flat");
      }
    }
  }

  private static final class CardSlot {
    private static final String FACE_DOWN_CARD = "__FACE_DOWN__";

    private final Div root = new Div();
    private final Image front = new Image();

    private String currentCard;
    private boolean faceUp;

    private CardSlot() {
      root.addClassName("poker-card-slot");

      Div inner = new Div();
      inner.addClassName("poker-card-inner");

      Image back = new Image("/assets/cards/back.svg", "Card back");
      back.addClassNames("poker-card-face", "poker-card-back");

      front.addClassNames("poker-card-face", "poker-card-front");
      front.setAlt("Card face");

      inner.add(back, front);
      root.add(inner);
    }

    private Div component() {
      return root;
    }

    private void clear() {
      currentCard = null;
      faceUp = false;
      root.addClassName("is-empty");
      root.removeClassName("is-face-up");
      front.setSrc("");
    }

    private void showFaceDown(int delayIndex, int delayStepMillis) {
      boolean changed = !Objects.equals(currentCard, FACE_DOWN_CARD) || faceUp;
      root.removeClassName("is-empty");
      if (changed) {
        triggerDealAnimation(delayIndex, true, delayStepMillis);
      }
      root.removeClassName("is-face-up");
      currentCard = FACE_DOWN_CARD;
      faceUp = false;
    }

    private void showCard(String cardCode, boolean revealFace, int delayIndex, int delayStepMillis) {
      if (cardCode == null || cardCode.isBlank()) {
        clear();
        return;
      }

      boolean changed = !Objects.equals(currentCard, cardCode);
      boolean revealChanged = faceUp != revealFace;

      if (changed) {
        front.setSrc(cardPath(cardCode));
      }

      root.removeClassName("is-empty");
      triggerDealAnimation(delayIndex, changed, delayStepMillis);

      if (revealFace) {
        if (changed || revealChanged) {
          root.removeClassName("is-face-up");
          long flipDelayMs = Math.round(delayIndex * (double) delayStepMillis + 120.0d);
          root.getElement().executeJs(
              "const el=this; const delay=$0; window.setTimeout(() => el.classList.add('is-face-up'), delay);",
              flipDelayMs
          );
        } else {
          root.addClassName("is-face-up");
        }
      } else {
        root.removeClassName("is-face-up");
      }

      currentCard = cardCode;
      faceUp = revealFace;
    }

    private void triggerDealAnimation(int delayIndex, boolean changed, int delayStepMillis) {
      if (!changed) {
        return;
      }

      String delay = String.format(Locale.ROOT, "%.3fs", Math.max(0, delayIndex) * (delayStepMillis / 1000.0d));
      root.getStyle().set("--deal-delay", delay);
      root.getElement().executeJs("const el=this; el.classList.remove('dealt'); void el.offsetWidth; el.classList.add('dealt');");
    }
  }
}
