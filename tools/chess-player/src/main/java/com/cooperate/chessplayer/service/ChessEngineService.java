package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.GameOutcome;
import com.cooperate.chessplayer.model.ReasoningEffort;
import com.github.bhlangonijr.chesslib.Board;
import com.github.bhlangonijr.chesslib.Side;
import com.github.bhlangonijr.chesslib.move.Move;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

@Component
public class ChessEngineService {
  private final OpenAiChessMoveClient openAiChessMoveClient;

  public ChessEngineService(OpenAiChessMoveClient openAiChessMoveClient) {
    this.openAiChessMoveClient = openAiChessMoveClient;
  }

  ChessEngineService() {
    this.openAiChessMoveClient = null;
  }

  public record MoveDecision(String uci, ChessColor nextToMove, String fenAfter) {
  }

  public record PositionAssessment(GameOutcome outcome, String reason) {
  }

  public String initialFen() {
    return new Board().getFen();
  }

  public MoveDecision nextMove(String fen, ChessColor sideToPlay) {
    return nextMove(fen, sideToPlay, ReasoningEffort.MEDIUM);
  }

  public MoveDecision nextMove(String fen, ChessColor sideToPlay, ReasoningEffort reasoningEffort) {
    Board board = loadBoard(fen);
    Side currentSide = board.getSideToMove();
    if (!ChessColor.fromSide(currentSide).equals(sideToPlay)) {
      throw new IllegalStateException("board side to move does not match local player side");
    }

    List<Move> legalMoves = board.legalMoves();
    if (legalMoves.isEmpty()) {
      throw new IllegalStateException("no legal moves available");
    }

    Move chosen = selectMove(board.getFen(), sideToPlay, legalMoves, reasoningEffort);

    if (!board.doMove(chosen)) {
      throw new IllegalStateException("selected move could not be applied: " + chosen);
    }

    return new MoveDecision(chosen.toString(), ChessColor.fromSide(board.getSideToMove()), board.getFen());
  }

  public PositionAssessment assess(String fen, int playedPlies, int maxPlies) {
    Board board = loadBoard(fen);

    if (board.isMated()) {
      ChessColor winner = ChessColor.fromSide(board.getSideToMove()).opposite();
      return new PositionAssessment(winner == ChessColor.WHITE ? GameOutcome.WHITE_WIN : GameOutcome.BLACK_WIN, "CHECKMATE");
    }

    if (board.isStaleMate()) {
      return new PositionAssessment(GameOutcome.DRAW, "STALEMATE");
    }

    if (board.isDraw() || board.isInsufficientMaterial() || board.isRepetition()) {
      return new PositionAssessment(GameOutcome.DRAW, "DRAW_RULE");
    }

    if (playedPlies >= maxPlies) {
      return new PositionAssessment(GameOutcome.DRAW, "MAX_PLIES");
    }

    return new PositionAssessment(GameOutcome.ONGOING, null);
  }

  public Board loadBoard(String fen) {
    Board board = new Board();
    if (fen != null && !fen.isBlank()) {
      board.loadFromFen(fen);
    }
    return board;
  }

  private Move selectMove(
      String fen,
      ChessColor sideToPlay,
      List<Move> legalMoves,
      ReasoningEffort reasoningEffort
  ) {
    if (openAiChessMoveClient != null) {
      List<String> legalMovesUci = legalMoves.stream()
          .map(Move::toString)
          .toList();
      String suggested = openAiChessMoveClient
          .chooseMove(fen, sideToPlay, legalMovesUci, reasoningEffort)
          .orElse(null);
      if (suggested != null) {
        for (Move legalMove : legalMoves) {
          if (legalMove.toString().equalsIgnoreCase(suggested)) {
            return legalMove;
          }
        }
      }
    }
    return fallbackMove(legalMoves);
  }

  private static Move fallbackMove(List<Move> legalMoves) {
    List<Move> sortedMoves = legalMoves.stream()
        .sorted(Comparator.comparing(Move::toString))
        .toList();
    int index = ThreadLocalRandom.current().nextInt(sortedMoves.size());
    return sortedMoves.get(index);
  }
}
