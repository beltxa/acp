import { Chessground } from 'chessground';
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import './chessground-board.css';

type Orientation = 'white' | 'black';
type ReducedMotionMode = 'off' | 'reduced' | 'system';

class ChessgroundBoardElement extends HTMLElement {
  private boardElement: HTMLDivElement | null = null;
  private ground: ReturnType<typeof Chessground> | null = null;
  private lastFen: string | null = null;
  private lastOrientation: Orientation = 'white';
  private lastHighlightKey: string | null = null;
  private reducedMotionMode: ReducedMotionMode = 'reduced';
  private pendingState:
    | {
        fen: string;
        orientation: Orientation;
        localFrom?: string | null;
        localTo?: string | null;
        remoteFrom?: string | null;
        remoteTo?: string | null;
        highlightKey: string | null;
      }
    | null = null;
  private rafId: number | null = null;
  private arrowOverlay: SVGSVGElement | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private arrowState:
    | {
        localFrom?: string | null;
        localTo?: string | null;
        remoteFrom?: string | null;
        remoteTo?: string | null;
        orientation: Orientation;
      }
    | null = null;

  connectedCallback() {
    if (this.ground) {
      return;
    }
    this.classList.add('chessground-host');

    this.boardElement = document.createElement('div');
    this.boardElement.className = 'cg-wrap brown cburnett';
    this.appendChild(this.boardElement);

    this.ground = Chessground(this.boardElement, {
      coordinates: true,
      viewOnly: true,
      orientation: 'white',
      animation: this.animationConfig(),
    });
    this.ensureArrowOverlay();
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => this.renderArrowsFromState());
      const board = this.currentBoardElement();
      if (board) {
        this.resizeObserver.observe(board);
      } else {
        this.resizeObserver.observe(this.boardElement);
      }
    }
  }

  disconnectedCallback() {
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
  }

  setReducedMotionMode(mode?: string | null) {
    const normalized = this.normalizeReducedMotion(mode);
    if (this.reducedMotionMode === normalized) {
      return;
    }
    this.reducedMotionMode = normalized;
  }

  setPosition(
    fen: string,
    orientation: Orientation,
    localFrom?: string | null,
    localTo?: string | null,
    remoteFrom?: string | null,
    remoteTo?: string | null,
  ) {
    if (!this.ground) {
      this.connectedCallback();
    }
    const localMoveKey = localFrom && localTo ? `${localFrom}:${localTo}` : null;
    const remoteMoveKey = remoteFrom && remoteTo ? `${remoteFrom}:${remoteTo}` : null;
    const highlightKey = [localMoveKey, remoteMoveKey].filter((value) => value !== null).join('|') || null;
    if (this.lastFen === fen && this.lastOrientation === orientation && this.lastHighlightKey === highlightKey) {
      return;
    }
    this.pendingState = { fen, orientation, localFrom, localTo, remoteFrom, remoteTo, highlightKey };
    if (this.rafId === null) {
      this.rafId = window.requestAnimationFrame(() => {
        this.rafId = null;
        this.flushPending();
      });
    }
  }

  private flushPending() {
    if (!this.ground || !this.pendingState) {
      return;
    }
    const state = this.pendingState;
    this.pendingState = null;

    const localLastMove = state.localFrom && state.localTo ? ([state.localFrom, state.localTo] as any) : undefined;
    this.ground.set({
      fen: state.fen,
      orientation: state.orientation,
      viewOnly: true,
      coordinates: true,
      animation: this.animationConfig(),
      highlight: {
        lastMove: true,
      },
      lastMove: localLastMove,
      drawable: {
        enabled: false,
        visible: true,
        autoShapes: [],
      },
    });
    this.arrowState = {
      localFrom: state.localFrom,
      localTo: state.localTo,
      remoteFrom: state.remoteFrom,
      remoteTo: state.remoteTo,
      orientation: state.orientation,
    };
    this.renderArrowsFromState();
    this.lastFen = state.fen;
    this.lastOrientation = state.orientation;
    this.lastHighlightKey = state.highlightKey;
  }

  private ensureArrowOverlay(): SVGSVGElement | null {
    const board = this.currentBoardElement();
    if (!board) {
      return null;
    }
    if (this.arrowOverlay && this.arrowOverlay.parentElement !== board) {
      this.arrowOverlay.remove();
      this.arrowOverlay = null;
    }
    if (this.arrowOverlay) {
      return this.arrowOverlay;
    }
    const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    overlay.classList.add('move-arrows-overlay');
    board.appendChild(overlay);
    this.arrowOverlay = overlay;
    return overlay;
  }

  private renderArrowsFromState() {
    if (!this.arrowState) {
      const overlay = this.ensureArrowOverlay();
      if (overlay) {
        overlay.replaceChildren();
      }
      return;
    }
    this.renderArrows(this.arrowState);
  }

  private renderArrows(state: {
    localFrom?: string | null;
    localTo?: string | null;
    remoteFrom?: string | null;
    remoteTo?: string | null;
    orientation: Orientation;
  }) {
    const overlay = this.ensureArrowOverlay();
    const board = this.currentBoardElement();
    if (!overlay || !board) {
      return;
    }
    overlay.replaceChildren();

    const boardSize = this.boardPixelSize(board);
    if (!boardSize) {
      return;
    }
    overlay.setAttribute('viewBox', `0 0 ${boardSize.width} ${boardSize.height}`);
    overlay.setAttribute('preserveAspectRatio', 'none');

    this.drawSquareHighlight(overlay, state.remoteFrom, state.orientation, boardSize, '#DC2626', '#B91C1C', 'opponent');
    if (state.remoteFrom !== state.remoteTo) {
      this.drawSquareHighlight(overlay, state.remoteTo, state.orientation, boardSize, '#DC2626', '#B91C1C', 'opponent');
    }

    this.drawArrow(overlay, state.localFrom, state.localTo, state.orientation, boardSize, '#15781B', 'local');
    this.drawArrow(overlay, state.remoteFrom, state.remoteTo, state.orientation, boardSize, '#B91C1C', 'opponent');
  }

  private drawArrow(
    overlay: SVGSVGElement,
    from: string | null | undefined,
    to: string | null | undefined,
    orientation: Orientation,
    boardSize: { width: number; height: number },
    color: string,
    kind: 'local' | 'opponent',
  ) {
    const fromCenter = this.squareCenter(from, orientation, boardSize);
    const toCenter = this.squareCenter(to, orientation, boardSize);
    if (!fromCenter || !toCenter) {
      return;
    }

    const dx = toCenter.x - fromCenter.x;
    const dy = toCenter.y - fromCenter.y;
    const length = Math.hypot(dx, dy);
    if (length < 1) {
      return;
    }

    const ux = dx / length;
    const uy = dy / length;
    const squareSize = Math.min(boardSize.width, boardSize.height) / 8;
    const tipInset = Math.max(2, squareSize * 0.045);
    const tipFromCenter = Math.max(8, squareSize * 0.5 - tipInset);
    const tipX = toCenter.x - ux * tipFromCenter;
    const tipY = toCenter.y - uy * tipFromCenter;

    const headLength = Math.max(5, squareSize * 0.11);
    const headWidth = Math.max(4, squareSize * 0.08) * 1.5;
    const shaftEndX = tipX - ux * headLength;
    const shaftEndY = tipY - uy * headLength;
    const lineWidth = Math.max(1.35, squareSize * 0.02) * 1.5;

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', fromCenter.x.toString());
    line.setAttribute('y1', fromCenter.y.toString());
    line.setAttribute('x2', shaftEndX.toString());
    line.setAttribute('y2', shaftEndY.toString());
    line.setAttribute('stroke', color);
    line.setAttribute('stroke-width', lineWidth.toString());
    line.setAttribute('stroke-linecap', 'round');
    line.setAttribute('class', `move-arrow-line ${kind}`);
    overlay.appendChild(line);

    const px = -uy;
    const py = ux;
    const baseX = tipX - ux * headLength;
    const baseY = tipY - uy * headLength;
    const leftX = baseX + px * (headWidth / 2);
    const leftY = baseY + py * (headWidth / 2);
    const rightX = baseX - px * (headWidth / 2);
    const rightY = baseY - py * (headWidth / 2);

    const head = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    head.setAttribute(
      'points',
      `${tipX},${tipY} ${leftX},${leftY} ${rightX},${rightY}`,
    );
    head.setAttribute('fill', color);
    head.setAttribute('class', `move-arrow-head ${kind}`);
    overlay.appendChild(head);
  }

  private drawSquareHighlight(
    overlay: SVGSVGElement,
    square: string | null | undefined,
    orientation: Orientation,
    boardSize: { width: number; height: number },
    fillColor: string,
    strokeColor: string,
    kind: 'local' | 'opponent',
  ) {
    const topLeft = this.squareTopLeft(square, orientation, boardSize);
    if (!topLeft) {
      return;
    }
    const squareWidth = boardSize.width / 8;
    const squareHeight = boardSize.height / 8;
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', (topLeft.x + 0.5).toString());
    rect.setAttribute('y', (topLeft.y + 0.5).toString());
    rect.setAttribute('width', Math.max(0, squareWidth - 1).toString());
    rect.setAttribute('height', Math.max(0, squareHeight - 1).toString());
    rect.setAttribute('fill', fillColor);
    rect.setAttribute('fill-opacity', '0.34');
    rect.setAttribute('stroke', strokeColor);
    rect.setAttribute('stroke-width', Math.max(1.4, Math.min(squareWidth, squareHeight) * 0.03).toString());
    rect.setAttribute('class', `move-square-highlight ${kind}`);
    overlay.appendChild(rect);
  }

  private squareCenter(
    square: string | null | undefined,
    orientation: Orientation,
    boardSize: { width: number; height: number },
  ): { x: number; y: number } | null {
    const topLeft = this.squareTopLeft(square, orientation, boardSize);
    if (!topLeft) {
      return null;
    }
    return {
      x: topLeft.x + boardSize.width / 16,
      y: topLeft.y + boardSize.height / 16,
    };
  }

  private squareTopLeft(
    square: string | null | undefined,
    orientation: Orientation,
    boardSize: { width: number; height: number },
  ): { x: number; y: number } | null {
    if (!this.isSquareKey(square)) {
      return null;
    }
    const file = square.charCodeAt(0) - 97;
    const rankIdx = Number.parseInt(square.substring(1), 10) - 1;
    const col = orientation === 'white' ? file : 7 - file;
    const row = orientation === 'white' ? 7 - rankIdx : rankIdx;
    const squareWidth = boardSize.width / 8;
    const squareHeight = boardSize.height / 8;
    return {
      x: col * squareWidth,
      y: row * squareHeight,
    };
  }

  private currentBoardElement(): HTMLElement | null {
    return (this.boardElement?.querySelector('cg-board') as HTMLElement | null) ?? null;
  }

  private boardPixelSize(board: HTMLElement): { width: number; height: number } | null {
    const clientWidth = board.clientWidth;
    const clientHeight = board.clientHeight;
    if (clientWidth > 0 && clientHeight > 0) {
      return { width: clientWidth, height: clientHeight };
    }
    const bounds = board.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) {
      return null;
    }
    return { width: bounds.width, height: bounds.height };
  }

  private isSquareKey(value?: string | null): value is string {
    return !!value && /^[a-h][1-8]$/.test(value);
  }

  private animationConfig() {
    if (this.shouldReduceMotion()) {
      return {
        enabled: false,
        duration: 0,
      };
    }
    return {
      enabled: true,
      duration: 240,
    };
  }

  private shouldReduceMotion(): boolean {
    if (this.reducedMotionMode === 'reduced') {
      return true;
    }
    if (this.reducedMotionMode === 'off') {
      return false;
    }
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  private normalizeReducedMotion(mode?: string | null): ReducedMotionMode {
    if (!mode) {
      return 'reduced';
    }
    const normalized = mode.trim().toLowerCase();
    if (normalized === 'off' || normalized === 'reduced' || normalized === 'system') {
      return normalized;
    }
    return 'reduced';
  }
}

customElements.define('chessground-board', ChessgroundBoardElement);
