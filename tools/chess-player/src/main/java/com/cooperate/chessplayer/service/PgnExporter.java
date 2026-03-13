package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.GameOutcome;
import com.cooperate.chessplayer.model.MatchState;
import com.github.bhlangonijr.chesslib.Side;
import com.github.bhlangonijr.chesslib.move.Move;
import com.github.bhlangonijr.chesslib.move.MoveList;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

@Component
public class PgnExporter {
  private static final Logger log = LoggerFactory.getLogger(PgnExporter.class);

  private final ChessPlayerProperties properties;

  public PgnExporter(ChessPlayerProperties properties) {
    this.properties = properties;
  }

  public void export(MatchState state) {
    if (state == null || !properties.isPgnExportEnabled() || state.getMatchId() == null) {
      return;
    }

    Path dir = Path.of(properties.getPgnExportDir());
    Path pgnPath = dir.resolve(state.getMatchId() + ".pgn");
    try {
      Files.createDirectories(dir);
      String pgn = buildPgn(state);
      Files.writeString(
          pgnPath,
          pgn,
          StandardOpenOption.CREATE,
          StandardOpenOption.TRUNCATE_EXISTING,
          StandardOpenOption.WRITE
      );
      log.info("Exported PGN for match {} to {}", state.getMatchId(), pgnPath);
    } catch (Exception e) {
      log.warn("Failed to export PGN for match {}", state.getMatchId(), e);
    }
  }

  private String buildPgn(MatchState state) {
    MoveList moveList = new MoveList();
    Side side = Side.WHITE;
    for (String uci : state.getMoveHistoryUci()) {
      moveList.add(new Move(uci, side));
      side = side == Side.WHITE ? Side.BLACK : Side.WHITE;
    }

    String moveText;
    try {
      moveText = moveList.toSanWithMoveNumbers();
    } catch (Exception e) {
      moveText = String.join(" ", state.getMoveHistoryUci());
    }

    String result = switch (state.getOutcome()) {
      case WHITE_WIN -> "1-0";
      case BLACK_WIN -> "0-1";
      case DRAW -> "1/2-1/2";
      case ONGOING -> "*";
    };

    StringBuilder sb = new StringBuilder();
    sb.append("[Event \"ACP Chess AI Match\"]\n");
    sb.append("[Site \"ACP Direct\"]\n");
    sb.append("[Round \"-\"]\n");
    sb.append("[White \"AI-White\"]\n");
    sb.append("[Black \"AI-Black\"]\n");
    sb.append("[Result \"").append(result).append("\"]\n");
    sb.append("[MatchId \"").append(state.getMatchId()).append("\"]\n");
    sb.append("[SessionId \"").append(state.getUcwId()).append("\"]\n");
    sb.append("\n");
    sb.append(moveText);
    if (!moveText.isBlank()) {
      sb.append(' ');
    }
    sb.append(result).append('\n');
    return sb.toString();
  }
}
