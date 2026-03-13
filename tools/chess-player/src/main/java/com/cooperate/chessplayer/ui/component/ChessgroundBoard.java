package com.cooperate.chessplayer.ui.component;

import com.cooperate.chessplayer.model.ChessColor;
import com.vaadin.flow.component.Component;
import com.vaadin.flow.component.Tag;
import com.vaadin.flow.component.dependency.JsModule;
import com.vaadin.flow.component.dependency.NpmPackage;

@Tag("chessground-board")
@JsModule("./chess/chessground-board.ts")
@NpmPackage(value = "chessground", version = "9.2.1")
public class ChessgroundBoard extends Component {

  public void setReducedMotionMode(String mode) {
    getElement().callJsFunction("setReducedMotionMode", mode);
  }

  public void setPosition(String fen, ChessColor orientation, String localLastMoveUci, String remoteLastMoveUci) {
    String boardOrientation = orientation == ChessColor.BLACK ? "black" : "white";
    String localFrom = null;
    String localTo = null;
    if (localLastMoveUci != null && localLastMoveUci.length() >= 4) {
      localFrom = localLastMoveUci.substring(0, 2);
      localTo = localLastMoveUci.substring(2, 4);
    }
    String remoteFrom = null;
    String remoteTo = null;
    if (remoteLastMoveUci != null && remoteLastMoveUci.length() >= 4) {
      remoteFrom = remoteLastMoveUci.substring(0, 2);
      remoteTo = remoteLastMoveUci.substring(2, 4);
    }
    getElement().callJsFunction("setPosition", fen, boardOrientation, localFrom, localTo, remoteFrom, remoteTo);
  }
}
