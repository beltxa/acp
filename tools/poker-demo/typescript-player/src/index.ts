import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import {
  AcpAgent,
  defaultAgentOptions,
  type DeliveryMode,
  type InboundResult,
  type JsonMap,
  type SendResult
} from "../../../../sdks/typescript/dist/index.js";

const POKER_PROFILE = "UCW_POKER_V1";
const OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses";
const LEGAL_ACTIONS = new Set(["FOLD", "CHECK", "CALL", "BET", "RAISE"]);

type Personality = {
  type: string;
  bluffFrequency: number;
  aggressionFactor: number;
  strategyHint: string;
};

type InboundEvent = {
  type: string;
  tableId?: string;
  handNumber?: number;
  payload: JsonMap;
};

type PlayerConfig = {
  serverPort: number;
  playerId: string;
  entityId: string;
  personality: string;
  llmProvider: string;
  model: string;
  localAgentId: string;
  dealerAgentId: string;
  publicBaseUrl: string;
  acpMessagePath: string;
  acpStorageDir: string;
  acpDiscoveryScheme: string;
  acpRelayUrl?: string;
  acpAllowInsecureHttp: boolean;
  acpAllowInsecureTls: boolean;
  acpCaFile?: string;
  acpDeliveryMode: DeliveryMode;
  actionTimeoutMillis: number;
  openaiApiKey?: string;
};

function env(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  return value && value.length > 0 ? value : fallback;
}

function boolEnv(name: string, fallback: boolean): boolean {
  const value = process.env[name]?.trim().toLowerCase();
  if (!value) {
    return fallback;
  }
  if (["1", "true", "yes", "on"].includes(value)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(value)) {
    return false;
  }
  return fallback;
}

function intEnv(name: string, fallback: number): number {
  const value = process.env[name]?.trim();
  if (!value) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
}

function parseDeliveryMode(raw: string): DeliveryMode {
  const normalized = raw.trim().toLowerCase();
  if (normalized === "auto" || normalized === "relay" || normalized === "amqp" || normalized === "mqtt") {
    return normalized;
  }
  return "direct";
}

function isJsonMap(value: unknown): value is JsonMap {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asInt(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return Math.trunc(parsed);
    }
  }
  return 0;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function normalizeActionName(value: unknown): string {
  const normalized = asString(value).toUpperCase();
  return LEGAL_ACTIONS.has(normalized) ? normalized : "";
}

function firstNonBlank(...values: Array<string | undefined>): string {
  for (const value of values) {
    if (value && value.trim().length > 0) {
      return value.trim();
    }
  }
  return "";
}

function loadConfig(): PlayerConfig {
  const relayUrl = process.env.POKER_PLAYER_ACP_RELAY_URL?.trim();
  const caFile = process.env.POKER_PLAYER_ACP_CA_FILE?.trim();
  const openaiApiKey = process.env.OPENAI_API_KEY?.trim();
  return {
    serverPort: intEnv("SERVER_PORT", 8091),
    playerId: env("POKER_PLAYER_PLAYER_ID", "Player-1"),
    entityId: env("POKER_PLAYER_ENTITY_ID", "Entity-A"),
    personality: env("POKER_PLAYER_PERSONALITY", "TIGHT_AGGRESSIVE"),
    llmProvider: env("POKER_PLAYER_LLM_PROVIDER", "openai"),
    model: env("POKER_PLAYER_MODEL", "chatgpt-5.2-instant"),
    localAgentId: env("POKER_PLAYER_LOCAL_AGENT_ID", "agent:player1@localhost:8091"),
    dealerAgentId: env("POKER_PLAYER_DEALER_AGENT_ID", "agent:dealer@localhost:8090"),
    publicBaseUrl: env("POKER_PLAYER_PUBLIC_BASE_URL", "http://localhost:8091"),
    acpMessagePath: env("POKER_PLAYER_ACP_MESSAGE_PATH", "/api/v1/acp/messages"),
    acpStorageDir: env("POKER_PLAYER_ACP_STORAGE_DIR", "/var/lib/poker-player/acp"),
    acpDiscoveryScheme: env("POKER_PLAYER_ACP_DISCOVERY_SCHEME", "http"),
    acpRelayUrl: relayUrl && relayUrl.length > 0 ? relayUrl : undefined,
    acpAllowInsecureHttp: boolEnv("POKER_PLAYER_ACP_ALLOW_INSECURE_HTTP", false),
    acpAllowInsecureTls: boolEnv("POKER_PLAYER_ACP_ALLOW_INSECURE_TLS", false),
    acpCaFile: caFile && caFile.length > 0 ? caFile : undefined,
    acpDeliveryMode: parseDeliveryMode(env("POKER_PLAYER_ACP_DELIVERY_MODE", "direct")),
    actionTimeoutMillis: Math.max(1000, intEnv("POKER_PLAYER_ACTION_TIMEOUT_MILLIS", 12000)),
    openaiApiKey: openaiApiKey && openaiApiKey.length > 0 ? openaiApiKey : undefined
  };
}

function resolveEndpoint(baseUrl: string, messagePath: string): string {
  const base = baseUrl.trim().replace(/\/+$/, "");
  const path = messagePath.startsWith("/") ? messagePath : `/${messagePath}`;
  return `${base}${path}`;
}

function resolvePersonality(configuredType: string, playerId: string): Personality {
  const normalized = configuredType.trim().toUpperCase();
  switch (normalized) {
    case "LOOSE_AGGRESSIVE":
      return {
        type: "LOOSE_AGGRESSIVE",
        bluffFrequency: 0.25,
        aggressionFactor: 0.88,
        strategyHint: "Contest many pots and apply pressure often."
      };
    case "CONSERVATIVE":
      return {
        type: "CONSERVATIVE",
        bluffFrequency: 0.05,
        aggressionFactor: 0.35,
        strategyHint: "Avoid marginal spots and preserve stack."
      };
    case "CHAOTIC":
      return {
        type: "CHAOTIC",
        bluffFrequency: 0.45,
        aggressionFactor: 0.92,
        strategyHint: "Mix in unpredictable aggression and occasional bluffs."
      };
    case "TIGHT_AGGRESSIVE":
      return {
        type: "TIGHT_AGGRESSIVE",
        bluffFrequency: 0.10,
        aggressionFactor: 0.78,
        strategyHint: "Play strong ranges and pressure with value-heavy raises."
      };
    default:
      break;
  }
  switch (playerId.trim().toLowerCase()) {
    case "player-1":
      return {
        type: "TIGHT_AGGRESSIVE",
        bluffFrequency: 0.10,
        aggressionFactor: 0.78,
        strategyHint: "Play strong ranges and pressure with value-heavy raises."
      };
    case "player-2":
      return {
        type: "LOOSE_AGGRESSIVE",
        bluffFrequency: 0.25,
        aggressionFactor: 0.88,
        strategyHint: "Contest many pots and apply pressure often."
      };
    case "player-3":
      return {
        type: "CONSERVATIVE",
        bluffFrequency: 0.05,
        aggressionFactor: 0.35,
        strategyHint: "Avoid marginal spots and preserve stack."
      };
    default:
      return {
        type: "CHAOTIC",
        bluffFrequency: 0.45,
        aggressionFactor: 0.92,
        strategyHint: "Mix in unpredictable aggression and occasional bluffs."
      };
  }
}

function legalActionList(request: JsonMap): string[] {
  return asStringList(request.legalActions).map((action) => normalizeActionName(action)).filter((action) => action.length > 0);
}

function actionPayload(action: string, amount: number, reason?: string): JsonMap {
  const payload: JsonMap = { action, amount: Math.max(0, amount) };
  if (reason && reason.trim()) {
    payload.reason = reason.trim();
  }
  return payload;
}

class DecisionEngine {
  private readonly config: PlayerConfig;

  public constructor(config: PlayerConfig) {
    this.config = config;
  }

  public async decideAction(request: JsonMap): Promise<JsonMap> {
    const personality = resolvePersonality(this.config.personality, this.config.playerId);
    const prompt = this.buildPrompt(request, personality);
    const raw = await this.generateOpenAIDecision(prompt);
    if (raw) {
      const parsed = this.parseResponse(raw, request);
      if (parsed) {
        return parsed;
      }
      return this.safeFallback(request, "invalid-response-fallback");
    }
    return this.ruleBasedFallback(request, personality, "local-safe-policy");
  }

  private buildPrompt(request: JsonMap, personality: Personality): string {
    const currentBet = Math.max(0, asInt(request.currentBet));
    const committedBet = Math.max(0, asInt(request.committedBet));
    const toCall = Math.max(0, currentBet - committedBet);
    return `Decide a single Texas Hold'em action for the current player.

Constraints:
- Return STRICT JSON object only.
- Use one of legal actions exactly.
- If action is BET or RAISE, amount must be total bet target for this round.

JSON format:
{"action":"FOLD|CHECK|CALL|BET|RAISE","amount":0,"reason":"short text"}

Context:
tableId=${asString(request.tableId)}
handNumber=${asInt(request.handNumber)}
round=${asString(request.roundType)}
playerId=${asString(request.playerId)}
holeCards=${JSON.stringify(asStringList(request.holeCards))}
communityCards=${JSON.stringify(asStringList(request.communityCards))}
pot=${Math.max(0, asInt(request.pot))}
currentBet=${currentBet}
committed=${committedBet}
toCall=${toCall}
stack=${Math.max(0, asInt(request.stack))}
minRaise=${Math.max(0, asInt(request.minRaise))}
legalActions=${JSON.stringify(legalActionList(request))}

Personality:
type=${personality.type}
bluffFrequency=${personality.bluffFrequency.toFixed(2)}
aggressionFactor=${personality.aggressionFactor.toFixed(2)}
strategyHint=${personality.strategyHint}`;
  }

  private async generateOpenAIDecision(prompt: string): Promise<string | undefined> {
    if (!prompt.trim()) {
      return undefined;
    }
    if (this.config.llmProvider.trim().toLowerCase() !== "openai") {
      return undefined;
    }
    if (!this.config.openaiApiKey) {
      return undefined;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.actionTimeoutMillis);
    try {
      const response = await fetch(OPENAI_RESPONSES_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.config.openaiApiKey}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          model: this.config.model || "chatgpt-5.2-instant",
          max_output_tokens: 220,
          text: { verbosity: "low" },
          input: [
            {
              role: "system",
              content: [{ type: "input_text", text: "You are a poker decision engine. Return strict JSON only." }]
            },
            {
              role: "user",
              content: [{ type: "input_text", text: prompt }]
            }
          ]
        }),
        signal: controller.signal
      });
      if (!response.ok) {
        console.warn(`OpenAI decision request failed with status ${response.status}`);
        return undefined;
      }
      const payload = await response.json();
      if (!isJsonMap(payload)) {
        return undefined;
      }
      return this.extractOutputText(payload);
    } catch (error) {
      console.warn("OpenAI decision request failed", error);
      return undefined;
    } finally {
      clearTimeout(timeout);
    }
  }

  private extractOutputText(payload: JsonMap): string | undefined {
    if (typeof payload.output_text === "string" && payload.output_text.trim()) {
      return payload.output_text.trim();
    }
    if (!Array.isArray(payload.output)) {
      return undefined;
    }
    const pieces: string[] = [];
    for (const item of payload.output) {
      if (!isJsonMap(item) || !Array.isArray(item.content)) {
        continue;
      }
      for (const part of item.content) {
        if (!isJsonMap(part) || typeof part.text !== "string") {
          continue;
        }
        const text = part.text.trim();
        if (text) {
          pieces.push(text);
        }
      }
    }
    return pieces.length > 0 ? pieces.join("\n") : undefined;
  }

  private parseResponse(rawResponse: string, request: JsonMap): JsonMap | undefined {
    let trimmed = rawResponse.trim();
    if (!trimmed) {
      return undefined;
    }
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) {
      trimmed = trimmed.slice(start, end + 1);
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return undefined;
    }
    if (!isJsonMap(parsed)) {
      return undefined;
    }
    const actionName = normalizeActionName(parsed.action);
    if (!actionName) {
      return undefined;
    }
    const action = actionPayload(actionName, Math.max(0, asInt(parsed.amount)), typeof parsed.reason === "string" ? parsed.reason : undefined);
    if (!this.isActionLegal(action, request)) {
      return undefined;
    }
    return this.normalizeAction(action, request);
  }

  private normalizeAction(action: JsonMap, request: JsonMap): JsonMap {
    const actionName = normalizeActionName(action.action);
    const reason = typeof action.reason === "string" ? action.reason : undefined;
    const currentBet = Math.max(0, asInt(request.currentBet));
    const committedBet = Math.max(0, asInt(request.committedBet));
    const minRaise = Math.max(0, asInt(request.minRaise));
    const stack = Math.max(0, asInt(request.stack));
    const toCall = Math.max(0, currentBet - committedBet);
    const amount = Math.max(0, asInt(action.amount));

    if (actionName === "FOLD" || actionName === "CHECK") {
      return actionPayload(actionName, 0, reason);
    }
    if (actionName === "CALL") {
      return actionPayload(actionName, Math.min(toCall, stack), reason);
    }
    if (actionName === "BET") {
      const minTarget = Math.max(minRaise, 1);
      const maxTarget = committedBet + stack;
      return actionPayload(actionName, Math.max(minTarget, Math.min(amount, maxTarget)), reason);
    }
    const minTarget = currentBet + minRaise;
    const maxTarget = committedBet + stack;
    return actionPayload("RAISE", Math.max(minTarget, Math.min(amount, maxTarget)), reason);
  }

  private isActionLegal(action: JsonMap, request: JsonMap): boolean {
    const legal = legalActionList(request);
    const actionName = normalizeActionName(action.action);
    if (!actionName || !legal.includes(actionName)) {
      return false;
    }
    const currentBet = Math.max(0, asInt(request.currentBet));
    const committedBet = Math.max(0, asInt(request.committedBet));
    const stack = Math.max(0, asInt(request.stack));
    const toCall = Math.max(0, currentBet - committedBet);
    switch (actionName) {
      case "FOLD":
        return true;
      case "CHECK":
        return toCall === 0;
      case "CALL":
        return stack > 0;
      case "BET":
        return currentBet === 0 && stack > 0;
      case "RAISE":
        return currentBet > 0 && stack + committedBet > currentBet;
      default:
        return false;
    }
  }

  private ruleBasedFallback(request: JsonMap, p: Personality, reasonTag: string): JsonMap {
    const legal = legalActionList(request);
    const pot = Math.max(0, asInt(request.pot));
    const currentBet = Math.max(0, asInt(request.currentBet));
    const committedBet = Math.max(0, asInt(request.committedBet));
    const minRaise = Math.max(0, asInt(request.minRaise));
    const stack = Math.max(0, asInt(request.stack));
    const toCall = Math.max(0, currentBet - committedBet);
    const aggressive = p.aggressionFactor >= 0.7;
    const bluffing = p.bluffFrequency >= 0.3;

    if (toCall === 0) {
      if (legal.includes("BET") && (aggressive || bluffing)) {
        const target = Math.min(committedBet + stack, Math.max(minRaise, minRaise + Math.trunc(pot / 6)));
        return { action: "BET", amount: Math.max(0, target), reason: `${reasonTag}: pressure bet` };
      }
      return { action: "CHECK", amount: 0, reason: `${reasonTag}: check` };
    }
    if (legal.includes("CALL") && aggressive && stack > toCall) {
      return { action: "CALL", amount: Math.min(toCall, stack), reason: `${reasonTag}: defend` };
    }
    return { action: "FOLD", amount: 0, reason: `${reasonTag}: fold` };
  }

  private safeFallback(request: JsonMap, reasonTag: string): JsonMap {
    const legal = legalActionList(request);
    const currentBet = Math.max(0, asInt(request.currentBet));
    const committedBet = Math.max(0, asInt(request.committedBet));
    const stack = Math.max(0, asInt(request.stack));
    const toCall = Math.max(0, currentBet - committedBet);

    if (toCall > 0 && legal.includes("FOLD")) {
      return { action: "FOLD", amount: 0, reason: `${reasonTag}: fold` };
    }
    if (legal.includes("CHECK")) {
      return { action: "CHECK", amount: 0, reason: `${reasonTag}: check` };
    }
    if (legal.includes("CALL")) {
      return { action: "CALL", amount: Math.min(toCall, stack), reason: `${reasonTag}: call` };
    }
    if (legal.length > 0) {
      return { action: legal[0], amount: 0, reason: `${reasonTag}: fallback` };
    }
    return { action: "FOLD", amount: 0, reason: `${reasonTag}: fallback` };
  }
}

class PokerRuntime {
  private readonly config: PlayerConfig;
  private readonly decision: DecisionEngine;
  private readonly agent: AcpAgent;
  private sequence = 0;
  private eliminated = false;
  private activeTableId?: string;
  private lastHandNumber = 0;
  private holeCards: string[] = [];

  public constructor(config: PlayerConfig, agent: AcpAgent) {
    this.config = config;
    this.agent = agent;
    this.decision = new DecisionEngine(config);
  }

  public async receive(rawMessage: JsonMap): Promise<InboundResult> {
    return this.agent.receive(rawMessage);
  }

  public async onInboundPayload(payload: JsonMap): Promise<void> {
    const event = this.parseInboundEvent(payload);
    if (!event.type || !event.payload) {
      return;
    }
    try {
      switch (event.type) {
        case "INVITATION": {
          const response = this.onInvitation(event.payload);
          await this.sendToDealer("JOIN_TABLE", event.tableId, event.handNumber, String(response.playerId ?? this.config.playerId), response);
          return;
        }
        case "HAND_START":
          this.lastHandNumber = Math.max(0, asInt((isJsonMap(event.payload.state) ? event.payload.state.handNumber : undefined)));
          console.log(`${this.config.playerId} received HAND_START for hand ${this.lastHandNumber}`);
          return;
        case "HOLE_CARDS":
          this.holeCards = asStringList(event.payload.holeCards);
          console.log(`${this.config.playerId} received hole cards ${JSON.stringify(this.holeCards)}`);
          return;
        case "ACTION_REQUEST": {
          const response = await this.onActionRequest(event.payload);
          await this.sendToDealer(
            "ACTION_RESPONSE",
            event.tableId,
            event.handNumber,
            String(response.playerId ?? this.config.playerId),
            response
          );
          return;
        }
        case "ACTION_APPLIED":
          console.log(`${this.config.playerId} observed action ${JSON.stringify(event.payload.action)}`);
          return;
        case "COMMUNITY_CARDS_UPDATED":
          console.log(`${this.config.playerId} observed community cards ${JSON.stringify(event.payload.communityCards)}`);
          return;
        case "HAND_RESULT":
          console.log(
            `${this.config.playerId} received hand result winners=${JSON.stringify(event.payload.winnerIds)} payouts=${JSON.stringify(event.payload.amountWonByPlayer)}`
          );
          return;
        case "PLAYER_ELIMINATED":
          if (asString(event.payload.playerId) === this.config.playerId) {
            this.eliminated = true;
            console.log(`${this.config.playerId} has been eliminated`);
          }
          return;
        case "GAME_FINISHED":
          console.log(
            `${this.config.playerId} received GAME_FINISHED winner=${JSON.stringify(event.payload.winnerId)} finalStacks=${JSON.stringify(event.payload.finalStacks)}`
          );
          return;
        default:
          return;
      }
    } catch (error) {
      console.warn(`Failed to process inbound payload for ${this.config.playerId}`, error);
    }
  }

  public getWellKnownDocument(): JsonMap {
    return this.agent.buildWellKnownDocument(this.config.publicBaseUrl);
  }

  public getIdentityPayload(): JsonMap {
    return { identity_document: this.agent.identity_document };
  }

  private onInvitation(message: JsonMap): JsonMap {
    const expectedPlayerId = asString(message.playerId);
    const accepted = this.config.playerId === expectedPlayerId;
    console.log(
      `${this.config.playerId} received INVITATION table=${String(message.tableId ?? "")} seat=${String(message.seatNumber ?? "")} expectedPlayerId='${expectedPlayerId}' accepted=${accepted}`
    );
    if (accepted) {
      this.activeTableId = asString(message.tableId);
      this.eliminated = false;
    }
    return {
      type: "JOIN_TABLE",
      tableId: message.tableId,
      playerId: this.config.playerId,
      seatNumber: Math.max(1, asInt(message.seatNumber)),
      accepted,
      message: accepted ? "joined" : "player id mismatch"
    };
  }

  private async onActionRequest(message: JsonMap): Promise<JsonMap> {
    let action: JsonMap;
    if (this.eliminated) {
      action = { action: "FOLD", amount: 0, reason: "eliminated" };
    } else {
      action = await this.decision.decideAction(message);
    }
    return {
      type: "ACTION_RESPONSE",
      tableId: message.tableId,
      playerId: this.config.playerId,
      action
    };
  }

  private async sendToDealer(
    messageType: string,
    tableId: string | undefined,
    handNumber: number | undefined,
    playerId: string,
    payload: JsonMap
  ): Promise<void> {
    const encoded = this.encodePayload(messageType, tableId, handNumber, playerId, payload);
    const context = `poker:${firstNonBlank(tableId, "table")}`;
    const result = await this.agent.send(
      [this.config.dealerAgentId],
      encoded,
      context,
      "SEND",
      300,
      undefined,
      undefined,
      this.config.acpDeliveryMode
    );
    if (this.isDelivered(result)) {
      return;
    }
    console.warn(`ACP send failed from ${this.config.playerId} to dealer: ${this.summarizeFailure(result)}`);
  }

  private encodePayload(
    messageType: string,
    tableId: string | undefined,
    handNumber: number | undefined,
    playerId: string,
    payload: JsonMap
  ): JsonMap {
    this.sequence += 1;
    return {
      profile: POKER_PROFILE,
      table_id: tableId ?? null,
      hand_number: handNumber ?? null,
      sequence: this.sequence,
      event_type: messageType,
      player_id: firstNonBlank(playerId, this.config.playerId),
      sent_at: new Date().toISOString(),
      payload
    };
  }

  private parseInboundEvent(payload: JsonMap): InboundEvent {
    if (asString(payload.profile) === POKER_PROFILE && typeof payload.event_type === "string" && isJsonMap(payload.payload)) {
      const body = payload.payload;
      const tableId = firstNonBlank(asString(payload.table_id), asString(body.tableId));
      const rawHand = payload.hand_number ?? body.handNumber;
      const hand = rawHand === undefined || rawHand === null ? undefined : asInt(rawHand);
      return {
        type: payload.event_type.trim().toUpperCase(),
        tableId: tableId || undefined,
        handNumber: hand,
        payload: body
      };
    }
    const handRaw = payload.handNumber;
    return {
      type: asString(payload.type).toUpperCase(),
      tableId: asString(payload.tableId) || undefined,
      handNumber: handRaw === undefined || handRaw === null ? undefined : asInt(handRaw),
      payload
    };
  }

  private isDelivered(result: SendResult): boolean {
    for (const outcome of result.outcomes) {
      if (outcome.state === "ACKNOWLEDGED" || outcome.state === "DELIVERED") {
        return true;
      }
    }
    return false;
  }

  private summarizeFailure(result: SendResult): string {
    if (result.outcomes.length === 0) {
      return "no delivery outcomes";
    }
    const first = result.outcomes[0];
    return `state=${String(first.state)}, reasonCode=${String(first.reason_code)}, detail=${String(first.detail)}`;
  }
}

async function buildRuntime(config: PlayerConfig): Promise<PokerRuntime> {
  const options = defaultAgentOptions();
  options.storage_dir = config.acpStorageDir;
  options.endpoint = resolveEndpoint(config.publicBaseUrl, config.acpMessagePath);
  options.discovery_scheme = config.acpDiscoveryScheme;
  options.allow_insecure_http = config.acpAllowInsecureHttp;
  options.allow_insecure_tls = config.acpAllowInsecureTls;
  options.default_delivery_mode = config.acpDeliveryMode;
  if (config.acpCaFile) {
    options.ca_file = config.acpCaFile;
  }
  if (config.acpRelayUrl) {
    options.relay_url = config.acpRelayUrl;
    options.relay_hints = [config.acpRelayUrl];
  }
  const agent = await AcpAgent.loadOrCreate(config.localAgentId, options);
  return new PokerRuntime(config, agent);
}

function writeJson(response: ServerResponse, statusCode: number, body: unknown): void {
  const encoded = Buffer.from(JSON.stringify(body ?? {}), "utf-8");
  response.statusCode = statusCode;
  response.setHeader("Content-Type", "application/json");
  response.setHeader("Content-Length", encoded.byteLength);
  response.end(encoded);
}

async function readJsonBody(request: IncomingMessage): Promise<JsonMap> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  const text = Buffer.concat(chunks).toString("utf-8").trim();
  if (!text) {
    return {};
  }
  const parsed = JSON.parse(text);
  if (!isJsonMap(parsed)) {
    throw new Error("payload must be a JSON object");
  }
  return parsed;
}

async function handleRequest(runtime: PokerRuntime, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const method = request.method ?? "GET";
  const url = new URL(request.url ?? "/", "http://localhost");
  const pathname = url.pathname;

  if (method === "GET" && pathname === "/.well-known/acp") {
    writeJson(response, 200, runtime.getWellKnownDocument());
    return;
  }
  if (method === "GET" && pathname === "/api/v1/acp/identity") {
    writeJson(response, 200, runtime.getIdentityPayload());
    return;
  }
  if (method === "POST" && pathname === "/api/v1/acp/messages") {
    try {
      const raw = await readJsonBody(request);
      const inbound = await runtime.receive(raw);
      writeJson(response, 200, inbound);
      if (isJsonMap(inbound.decrypted_payload)) {
        void runtime.onInboundPayload(inbound.decrypted_payload).catch((error) => {
          console.warn("Failed to process inbound payload", error);
        });
      }
      return;
    } catch (error) {
      writeJson(response, 400, { error: String(error) });
      return;
    }
  }
  writeJson(response, 404, { error: "not found" });
}

async function main(): Promise<void> {
  const config = loadConfig();
  const runtime = await buildRuntime(config);
  console.log(
    `Player ${config.playerId} (${config.entityId}) started with provider=${config.llmProvider} model=${config.model} personality=${config.personality} localAgentId=${config.localAgentId}`
  );

  const server = createServer((request, response) => {
    void handleRequest(runtime, request, response);
  });
  server.listen(config.serverPort, "0.0.0.0", () => {
    console.log(`TypeScript poker player listening on 0.0.0.0:${config.serverPort}`);
  });
}

void main();
