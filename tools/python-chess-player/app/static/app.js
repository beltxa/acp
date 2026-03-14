(() => {
  const INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
  const PIECE_TO_GLYPH = {
    K: "♔",
    Q: "♕",
    R: "♖",
    B: "♗",
    N: "♘",
    P: "♙",
    k: "♚",
    q: "♛",
    r: "♜",
    b: "♝",
    n: "♞",
    p: "♟",
  };

  const body = document.body;
  const boot = {
    localAgentId: body.dataset.localAgentId,
    remoteAgentId: body.dataset.remoteAgentId,
    localDisplayName: body.dataset.localDisplayName,
    remoteDisplayName: body.dataset.remoteDisplayName,
    defaultColor: (body.dataset.defaultColor || "WHITE").toUpperCase(),
    defaultEffort: (body.dataset.defaultEffort || "medium").toLowerCase(),
  };

  const ui = {
    localEntity: document.getElementById("local-entity"),
    players: document.getElementById("players"),
    status: document.getElementById("status"),
    movesBody: document.getElementById("moves-body"),
    board: document.getElementById("board"),
    topPlayer: document.getElementById("top-player-name"),
    bottomPlayer: document.getElementById("bottom-player-name"),
    topTurnDot: document.getElementById("top-turn-dot"),
    bottomTurnDot: document.getElementById("bottom-turn-dot"),
    topCapturedLabel: document.getElementById("top-captured-label"),
    bottomCapturedLabel: document.getElementById("bottom-captured-label"),
    topCaptured: document.getElementById("top-captured"),
    bottomCaptured: document.getElementById("bottom-captured"),
    effort: document.getElementById("reasoning-effort"),
    startButton: document.getElementById("start-button"),
    playAgainButton: document.getElementById("play-again-button"),
  };

  let trackedMatchId = null;
  let nextReasoningEffort = boot.defaultEffort;
  let pollIntervalMs = 2000;

  const DEFAULT_COUNTS = {
    white: { P: 8, N: 2, B: 2, R: 2, Q: 1 },
    black: { p: 8, n: 2, b: 2, r: 2, q: 1 },
  };

  function toFriendlyName(agentId, displayName) {
    if (displayName && displayName.trim()) {
      return displayName.trim();
    }
    if (!agentId || !agentId.trim()) {
      return "AI Player";
    }
    let normalized = agentId.trim();
    if (normalized.startsWith("agent:")) {
      normalized = normalized.slice("agent:".length);
    }
    const at = normalized.indexOf("@");
    if (at > 0) {
      normalized = normalized.slice(0, at);
    }
    return normalized || "AI Player";
  }

  function statusIsInProgress(matchState) {
    if (!matchState) {
      return false;
    }
    const status = String(matchState.status || "").toUpperCase();
    if (status === "ACTIVE" || status === "INVITED" || status === "COMPLETING") {
      return true;
    }
    const ucw = String(matchState.ucwStatus || "").toUpperCase();
    return (
      ucw === "ACTIVE"
      || ucw === "FROZEN"
      || ucw === "COMPLETING"
      || ucw === "PENDING"
      || ucw === "INVITED_PENDING"
    );
  }

  function parseFenPieces(fen) {
    const boardPart = String(fen || INITIAL_FEN).split(" ")[0];
    const ranks = boardPart.split("/");
    const squares = {};
    for (let rankIndex = 0; rankIndex < 8; rankIndex += 1) {
      const rank = 8 - rankIndex;
      let file = 0;
      for (const token of ranks[rankIndex] || "") {
        if (/\d/.test(token)) {
          file += Number(token);
          continue;
        }
        const square = `${String.fromCharCode(97 + file)}${rank}`;
        squares[square] = token;
        file += 1;
      }
    }
    return squares;
  }

  function renderBoard(fen, orientation, localMoveUci, remoteMoveUci) {
    const squares = parseFenPieces(fen);
    const localHighlights = new Set(moveSquares(localMoveUci));
    const remoteHighlights = new Set(moveSquares(remoteMoveUci));
    const isBlackOrientation = String(orientation || "WHITE").toUpperCase() === "BLACK";
    const ranks = isBlackOrientation ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
    const files = isBlackOrientation ? ["h", "g", "f", "e", "d", "c", "b", "a"] : ["a", "b", "c", "d", "e", "f", "g", "h"];

    ui.board.innerHTML = "";
    for (const rank of ranks) {
      for (let fileIndex = 0; fileIndex < files.length; fileIndex += 1) {
        const file = files[fileIndex];
        const squareName = `${file}${rank}`;
        const piece = squares[squareName];
        const pieceGlyph = piece ? PIECE_TO_GLYPH[piece] || "" : "";
        const actualFile = file.charCodeAt(0) - 96;
        const isLight = ((actualFile + rank) % 2) === 0;

        const square = document.createElement("div");
        square.className = `square ${isLight ? "light" : "dark"}`;
        if (localHighlights.has(squareName)) {
          square.classList.add("highlight-local");
        } else if (remoteHighlights.has(squareName)) {
          square.classList.add("highlight-remote");
        }
        square.textContent = pieceGlyph;
        ui.board.appendChild(square);
      }
    }
  }

  function moveSquares(uci) {
    if (!uci || uci.length < 4) {
      return [];
    }
    return [uci.slice(0, 2).toLowerCase(), uci.slice(2, 4).toLowerCase()];
  }

  function sideToMoveFromFen(fen) {
    const turnToken = String(fen || "").split(" ")[1] || "w";
    return turnToken === "b" ? "BLACK" : "WHITE";
  }

  function resolveHighlightMoves(history, localColor) {
    if (!Array.isArray(history) || history.length === 0) {
      return { localMoveUci: null, remoteMoveUci: null };
    }
    const normalized = String(localColor || "WHITE").toUpperCase();
    for (let index = history.length - 1; index >= 0; index -= 1) {
      const move = history[index];
      if (!move || move.length < 4) {
        continue;
      }
      const moveSide = (index % 2 === 0) ? "WHITE" : "BLACK";
      if (moveSide === normalized) {
        return { localMoveUci: move, remoteMoveUci: null };
      }
      return { localMoveUci: null, remoteMoveUci: move };
    }
    return { localMoveUci: null, remoteMoveUci: null };
  }

  function computeCapturedFromFen(fen) {
    const squares = parseFenPieces(fen);
    const whiteCounts = { P: 0, N: 0, B: 0, R: 0, Q: 0 };
    const blackCounts = { p: 0, n: 0, b: 0, r: 0, q: 0 };

    Object.values(squares).forEach((piece) => {
      if (whiteCounts[piece] !== undefined) {
        whiteCounts[piece] += 1;
      } else if (blackCounts[piece] !== undefined) {
        blackCounts[piece] += 1;
      }
    });

    const capturedByWhite = [];
    const capturedByBlack = [];
    ["q", "r", "b", "n", "p"].forEach((piece) => {
      const missing = Math.max(0, DEFAULT_COUNTS.black[piece] - blackCounts[piece]);
      for (let i = 0; i < missing; i += 1) {
        capturedByWhite.push(PIECE_TO_GLYPH[piece]);
      }
    });
    ["Q", "R", "B", "N", "P"].forEach((piece) => {
      const missing = Math.max(0, DEFAULT_COUNTS.white[piece] - whiteCounts[piece]);
      for (let i = 0; i < missing; i += 1) {
        capturedByBlack.push(PIECE_TO_GLYPH[piece]);
      }
    });
    return { byWhite: capturedByWhite, byBlack: capturedByBlack };
  }

  function renderCapturedPieces(localOrientation, whiteName, blackName, captured) {
    const localBottomIsWhite = String(localOrientation || "WHITE").toUpperCase() !== "BLACK";
    const topName = localBottomIsWhite ? blackName : whiteName;
    const bottomName = localBottomIsWhite ? whiteName : blackName;
    const topCaptured = localBottomIsWhite ? captured.byBlack : captured.byWhite;
    const bottomCaptured = localBottomIsWhite ? captured.byWhite : captured.byBlack;

    ui.topCapturedLabel.textContent = `${topName} captured`;
    ui.bottomCapturedLabel.textContent = `${bottomName} captured`;
    ui.topCaptured.textContent = topCaptured.length ? topCaptured.join(" ") : "-";
    ui.bottomCaptured.textContent = bottomCaptured.length ? bottomCaptured.join(" ") : "-";
  }

  function renderBoardSideLabels(localOrientation, whiteName, blackName, sideToMove) {
    const localBottomIsWhite = String(localOrientation || "WHITE").toUpperCase() !== "BLACK";
    const topName = localBottomIsWhite ? blackName : whiteName;
    const bottomName = localBottomIsWhite ? whiteName : blackName;
    const topColor = localBottomIsWhite ? "BLACK" : "WHITE";
    const bottomColor = localBottomIsWhite ? "WHITE" : "BLACK";

    ui.topPlayer.textContent = topName;
    ui.bottomPlayer.textContent = bottomName;
    ui.topTurnDot.style.visibility = (sideToMove === topColor) ? "visible" : "hidden";
    ui.bottomTurnDot.style.visibility = (sideToMove === bottomColor) ? "visible" : "hidden";
  }

  function renderMoves(history) {
    const safeHistory = Array.isArray(history) ? history : [];
    ui.movesBody.innerHTML = "";
    for (let index = 0; index < safeHistory.length; index += 2) {
      const row = document.createElement("tr");
      const moveNumber = (index / 2) + 1;
      const whiteMove = safeHistory[index] || "";
      const blackMove = safeHistory[index + 1] || "";

      row.innerHTML = `
        <td>${moveNumber}</td>
        <td>${whiteMove}</td>
        <td class="${blackMove ? "black-cell" : ""}">${blackMove}</td>
      `;
      ui.movesBody.appendChild(row);
    }
  }

  function renderIdle() {
    const localName = toFriendlyName(boot.localAgentId, boot.localDisplayName);
    const remoteName = toFriendlyName(boot.remoteAgentId, boot.remoteDisplayName);
    const localColor = boot.defaultColor;
    const white = localColor === "WHITE" ? localName : remoteName;
    const black = localColor === "WHITE" ? remoteName : localName;

    ui.localEntity.textContent = `Local entity: ${localName}`;
    ui.players.textContent = `${white} (White) vs ${black} (Black)`;
    ui.status.textContent = "No active game";
    renderMoves([]);
    renderBoard(INITIAL_FEN, localColor, null, null);
    renderCapturedPieces(localColor, white, black, { byWhite: [], byBlack: [] });
    renderBoardSideLabels(localColor, white, black, "WHITE");

    ui.effort.value = nextReasoningEffort;
    ui.effort.disabled = false;
    ui.startButton.classList.remove("hidden");
    ui.playAgainButton.classList.add("hidden");
  }

  function renderMatch(state) {
    const localName = toFriendlyName(state.localParticipantUrn, state.localUserUrn);
    const remoteName = toFriendlyName(state.remoteParticipantUrn, state.remoteUserUrn);
    const localColor = String(state.localColor || boot.defaultColor).toUpperCase();
    const white = localColor === "WHITE" ? localName : remoteName;
    const black = localColor === "WHITE" ? remoteName : localName;
    const history = Array.isArray(state.moveHistoryUci) ? state.moveHistoryUci : [];
    const fen = state.currentFen && String(state.currentFen).trim() ? state.currentFen : INITIAL_FEN;

    ui.localEntity.textContent = `Local entity: ${localName}`;
    ui.players.textContent = `${white} (White) vs ${black} (Black)`;

    const sessionId = state.ucwId || "-";
    const matchStatus = state.status || "UNKNOWN";
    let statusText = `Session: ${sessionId} | Match: ${matchStatus}`;
    const effort = String(state.reasoningEffort || "MEDIUM").toLowerCase();
    statusText += ` | Effort: ${effort}`;
    if (state.outcome && state.outcome !== "ONGOING") {
      statusText += ` | Result: ${state.outcome}`;
    }
    ui.status.textContent = statusText;

    const highlight = resolveHighlightMoves(history, localColor);
    renderBoard(fen, localColor, highlight.localMoveUci, highlight.remoteMoveUci);
    renderBoardSideLabels(localColor, white, black, sideToMoveFromFen(fen));
    renderCapturedPieces(localColor, white, black, computeCapturedFromFen(fen));
    renderMoves(history);

    const inProgress = statusIsInProgress(state) || state.outcome === "ONGOING";
    ui.effort.value = inProgress ? effort : nextReasoningEffort;
    ui.effort.disabled = inProgress;
    if (!inProgress && state.status === "COMPLETED") {
      ui.startButton.classList.add("hidden");
      ui.playAgainButton.classList.remove("hidden");
    } else if (!inProgress) {
      ui.startButton.classList.remove("hidden");
      ui.playAgainButton.classList.add("hidden");
    } else {
      ui.startButton.classList.add("hidden");
      ui.playAgainButton.classList.add("hidden");
    }
  }

  function parseTimestamp(value) {
    const ts = Date.parse(value || "");
    return Number.isNaN(ts) ? 0 : ts;
  }

  function resolveDisplayState(matches) {
    if (!Array.isArray(matches) || matches.length === 0) {
      trackedMatchId = null;
      return null;
    }

    if (trackedMatchId) {
      const tracked = matches.find((item) => item && item.ucwId === trackedMatchId);
      if (tracked) {
        return tracked;
      }
    }

    const active = matches
      .filter((item) => statusIsInProgress(item))
      .sort((a, b) => {
        const aUpdated = parseTimestamp(a.updatedAt);
        const bUpdated = parseTimestamp(b.updatedAt);
        if (aUpdated !== bUpdated) {
          return bUpdated - aUpdated;
        }
        return parseTimestamp(b.createdAt) - parseTimestamp(a.createdAt);
      });

    if (active.length > 0) {
      trackedMatchId = active[0].ucwId || null;
      return active[0];
    }

    trackedMatchId = null;
    return null;
  }

  async function getJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    return response.json();
  }

  async function postJson(url, bodyPayload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(bodyPayload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail || `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }

  async function refresh() {
    try {
      const matches = await getJson("/api/v1/chess/matches");
      const state = resolveDisplayState(matches);
      if (!state) {
        renderIdle();
        return;
      }
      trackedMatchId = state.ucwId || trackedMatchId;
      renderMatch(state);
    } catch (error) {
      ui.status.textContent = `Error: ${error.message}`;
    }
  }

  async function startGame() {
    const effort = (ui.effort.value || "medium").toLowerCase();
    nextReasoningEffort = effort;
    try {
      const result = await postJson("/api/v1/chess/matches/start", { reasoning_effort: effort });
      trackedMatchId = result.session_id || result.match_id || trackedMatchId;
      await refresh();
    } catch (error) {
      ui.status.textContent = `Unable to start game: ${error.message}`;
    }
  }

  async function bootstrap() {
    try {
      const config = await getJson("/api/v1/chess/config");
      if (typeof config.poll_interval_ms === "number" && config.poll_interval_ms > 0) {
        pollIntervalMs = config.poll_interval_ms;
      }
    } catch (error) {
      // Continue with defaults.
    }

    ui.effort.value = nextReasoningEffort;
    ui.startButton.addEventListener("click", startGame);
    ui.playAgainButton.addEventListener("click", startGame);
    ui.effort.addEventListener("change", () => {
      nextReasoningEffort = (ui.effort.value || "medium").toLowerCase();
    });

    await refresh();
    setInterval(refresh, Math.max(250, pollIntervalMs));
  }

  bootstrap();
})();
