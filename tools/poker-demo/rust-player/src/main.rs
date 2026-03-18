use std::env;
use std::sync::mpsc::{self, Sender};
use std::time::{Duration, Instant};

use acp_runtime::{
    AcpAgent, AcpAgentOptions, DeliveryMode, DeliveryState, InboundResult, MessageClass,
    SendResult,
};
use chrono::{SecondsFormat, Utc};
use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{Map, Value, json};
use tiny_http::{Header, Method, Request, Response, Server, StatusCode};

type JsonMap = Map<String, Value>;

const POKER_PROFILE: &str = "UCW_POKER_V1";
const OPENAI_RESPONSES_URL: &str = "https://api.openai.com/v1/responses";

#[derive(Clone)]
struct Config {
    server_port: u16,
    player_id: String,
    entity_id: String,
    personality: String,
    llm_provider: String,
    model: String,
    local_agent_id: String,
    dealer_agent_id: String,
    public_base_url: String,
    acp_message_path: String,
    acp_storage_dir: String,
    acp_discovery_scheme: String,
    acp_relay_url: Option<String>,
    acp_allow_insecure_http: bool,
    acp_allow_insecure_tls: bool,
    acp_ca_file: Option<String>,
    acp_delivery_mode: DeliveryMode,
    action_timeout_millis: u64,
    openai_api_key: Option<String>,
}

#[derive(Clone)]
struct Personality {
    kind: String,
    bluff_frequency: f64,
    aggression_factor: f64,
    strategy_hint: String,
}

struct DecisionEngine {
    config: Config,
    http: Client,
}

struct PokerRuntime {
    config: Config,
    agent: AcpAgent,
    decision_engine: DecisionEngine,
    sequence: i64,
    eliminated: bool,
    active_table_id: Option<String>,
    last_hand_number: i64,
    hole_cards: Vec<String>,
}

struct InboundEvent {
    event_type: String,
    table_id: Option<String>,
    hand_number: Option<i64>,
    payload: JsonMap,
}

#[derive(Clone)]
struct ServerState {
    inbound_tx: Sender<JsonMap>,
    well_known_document: JsonMap,
    identity_payload: JsonMap,
}

fn main() {
    let config = load_config();
    let mut runtime = match PokerRuntime::new(config.clone()) {
        Ok(runtime) => runtime,
        Err(error) => {
            eprintln!("unable to initialize ACP agent: {error}");
            std::process::exit(1);
        }
    };

    println!(
        "Player {} ({}) started with provider={} model={} personality={} localAgentId={}",
        config.player_id,
        config.entity_id,
        config.llm_provider,
        config.model,
        config.personality,
        config.local_agent_id
    );

    let bind = format!("0.0.0.0:{}", config.server_port);
    let server = match Server::http(&bind) {
        Ok(server) => server,
        Err(error) => {
            eprintln!("unable to bind server on {bind}: {error}");
            std::process::exit(1);
        }
    };
    println!("Rust poker player listening on {}", bind);

    let well_known_document = match runtime.get_well_known_document() {
        Ok(payload) => payload,
        Err(error) => {
            eprintln!("unable to build ACP well-known document: {error}");
            std::process::exit(1);
        }
    };
    let identity_payload = runtime.get_identity_payload();

    let (inbound_tx, inbound_rx) = mpsc::channel::<JsonMap>();
    std::thread::spawn(move || run_inbound_worker(runtime, inbound_rx));

    let server_state = ServerState {
        inbound_tx,
        well_known_document,
        identity_payload,
    };

    for request in server.incoming_requests() {
        handle_request(&server_state, request);
    }
}

fn load_config() -> Config {
    let relay_url = non_blank_env("POKER_PLAYER_ACP_RELAY_URL");
    let ca_file = non_blank_env("POKER_PLAYER_ACP_CA_FILE");
    let openai_api_key = non_blank_env("OPENAI_API_KEY");
    Config {
        server_port: int_env("SERVER_PORT", 8091).max(1) as u16,
        player_id: env_or("POKER_PLAYER_PLAYER_ID", "Player-1"),
        entity_id: env_or("POKER_PLAYER_ENTITY_ID", "Entity-A"),
        personality: env_or("POKER_PLAYER_PERSONALITY", "TIGHT_AGGRESSIVE"),
        llm_provider: env_or("POKER_PLAYER_LLM_PROVIDER", "openai"),
        model: env_or("POKER_PLAYER_MODEL", "chatgpt-5.2-instant"),
        local_agent_id: env_or("POKER_PLAYER_LOCAL_AGENT_ID", "agent:player1@localhost:8091"),
        dealer_agent_id: env_or("POKER_PLAYER_DEALER_AGENT_ID", "agent:dealer@localhost:8090"),
        public_base_url: env_or("POKER_PLAYER_PUBLIC_BASE_URL", "http://localhost:8091"),
        acp_message_path: env_or("POKER_PLAYER_ACP_MESSAGE_PATH", "/api/v1/acp/messages"),
        acp_storage_dir: env_or("POKER_PLAYER_ACP_STORAGE_DIR", "/var/lib/poker-player/acp"),
        acp_discovery_scheme: env_or("POKER_PLAYER_ACP_DISCOVERY_SCHEME", "http"),
        acp_relay_url: relay_url,
        acp_allow_insecure_http: bool_env("POKER_PLAYER_ACP_ALLOW_INSECURE_HTTP", false),
        acp_allow_insecure_tls: bool_env("POKER_PLAYER_ACP_ALLOW_INSECURE_TLS", false),
        acp_ca_file: ca_file,
        acp_delivery_mode: parse_delivery_mode(&env_or("POKER_PLAYER_ACP_DELIVERY_MODE", "direct")),
        action_timeout_millis: int_env("POKER_PLAYER_ACTION_TIMEOUT_MILLIS", 12000).max(1000) as u64,
        openai_api_key,
    }
}

fn env_or(name: &str, fallback: &str) -> String {
    let value = env::var(name).unwrap_or_default();
    let trimmed = value.trim();
    if trimmed.is_empty() {
        fallback.to_string()
    } else {
        trimmed.to_string()
    }
}

fn non_blank_env(name: &str) -> Option<String> {
    let value = env::var(name).unwrap_or_default();
    let trimmed = value.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn bool_env(name: &str, fallback: bool) -> bool {
    let value = env::var(name).unwrap_or_default();
    match value.trim().to_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => true,
        "0" | "false" | "no" | "off" => false,
        _ => fallback,
    }
}

fn int_env(name: &str, fallback: i64) -> i64 {
    let value = env::var(name).unwrap_or_default();
    value.trim().parse::<i64>().unwrap_or(fallback)
}

fn parse_delivery_mode(raw: &str) -> DeliveryMode {
    match raw.trim().to_lowercase().as_str() {
        "auto" => DeliveryMode::Auto,
        "relay" => DeliveryMode::Relay,
        "amqp" => DeliveryMode::Amqp,
        "mqtt" => DeliveryMode::Mqtt,
        _ => DeliveryMode::Direct,
    }
}

fn resolve_endpoint(base_url: &str, message_path: &str) -> String {
    let base = base_url.trim().trim_end_matches('/');
    let path = if message_path.starts_with('/') {
        message_path.to_string()
    } else {
        format!("/{}", message_path)
    };
    format!("{base}{path}")
}

fn as_string(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or_default()
}

fn as_i64(value: Option<&Value>) -> i64 {
    match value {
        Some(Value::Number(number)) => number.as_i64().or_else(|| number.as_u64().map(|v| v as i64)).unwrap_or(0),
        Some(Value::String(text)) => text.trim().parse::<i64>().unwrap_or(0),
        Some(Value::Bool(flag)) => i64::from(*flag),
        _ => 0,
    }
}

fn as_string_list(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str())
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn normalize_action_name(value: Option<&Value>) -> Option<String> {
    let normalized = as_string(value).to_uppercase();
    match normalized.as_str() {
        "FOLD" | "CHECK" | "CALL" | "BET" | "RAISE" => Some(normalized),
        _ => None,
    }
}

fn first_non_blank(values: &[Option<String>]) -> Option<String> {
    values.iter().flatten().find(|value| !value.trim().is_empty()).cloned()
}

fn action_map(action: &str, amount: i64, reason: Option<String>) -> JsonMap {
    let mut action_map = JsonMap::new();
    action_map.insert("action".to_string(), Value::String(action.to_string()));
    action_map.insert("amount".to_string(), Value::from(amount.max(0)));
    if let Some(reason_text) = reason {
        action_map.insert("reason".to_string(), Value::String(reason_text));
    }
    action_map
}

fn legal_action_list(request: &JsonMap) -> Vec<String> {
    as_string_list(request.get("legalActions"))
        .into_iter()
        .filter_map(|action| normalize_action_name(Some(&Value::String(action))))
        .collect()
}

fn contains_action(actions: &[String], target: &str) -> bool {
    actions.iter().any(|action| action == target)
}

fn resolve_personality(configured_type: &str, player_id: &str) -> Personality {
    match configured_type.trim().to_uppercase().as_str() {
        "LOOSE_AGGRESSIVE" => Personality {
            kind: "LOOSE_AGGRESSIVE".to_string(),
            bluff_frequency: 0.25,
            aggression_factor: 0.88,
            strategy_hint: "Contest many pots and apply pressure often.".to_string(),
        },
        "CONSERVATIVE" => Personality {
            kind: "CONSERVATIVE".to_string(),
            bluff_frequency: 0.05,
            aggression_factor: 0.35,
            strategy_hint: "Avoid marginal spots and preserve stack.".to_string(),
        },
        "CHAOTIC" => Personality {
            kind: "CHAOTIC".to_string(),
            bluff_frequency: 0.45,
            aggression_factor: 0.92,
            strategy_hint: "Mix in unpredictable aggression and occasional bluffs.".to_string(),
        },
        "TIGHT_AGGRESSIVE" => Personality {
            kind: "TIGHT_AGGRESSIVE".to_string(),
            bluff_frequency: 0.10,
            aggression_factor: 0.78,
            strategy_hint: "Play strong ranges and pressure with value-heavy raises.".to_string(),
        },
        _ => match player_id.trim().to_lowercase().as_str() {
            "player-1" => Personality {
                kind: "TIGHT_AGGRESSIVE".to_string(),
                bluff_frequency: 0.10,
                aggression_factor: 0.78,
                strategy_hint: "Play strong ranges and pressure with value-heavy raises.".to_string(),
            },
            "player-2" => Personality {
                kind: "LOOSE_AGGRESSIVE".to_string(),
                bluff_frequency: 0.25,
                aggression_factor: 0.88,
                strategy_hint: "Contest many pots and apply pressure often.".to_string(),
            },
            "player-3" => Personality {
                kind: "CONSERVATIVE".to_string(),
                bluff_frequency: 0.05,
                aggression_factor: 0.35,
                strategy_hint: "Avoid marginal spots and preserve stack.".to_string(),
            },
            _ => Personality {
                kind: "CHAOTIC".to_string(),
                bluff_frequency: 0.45,
                aggression_factor: 0.92,
                strategy_hint: "Mix in unpredictable aggression and occasional bluffs.".to_string(),
            },
        },
    }
}

impl DecisionEngine {
    fn new(config: Config) -> Self {
        Self {
            config,
            http: Client::builder().build().unwrap_or_else(|_| Client::new()),
        }
    }

    fn decide_action(&self, request: &JsonMap) -> JsonMap {
        let personality = resolve_personality(&self.config.personality, &self.config.player_id);
        let prompt = self.build_prompt(request, &personality);
        if let Some(raw_response) = self.generate_openai_decision(&prompt) {
            if let Some(parsed) = self.parse_response(&raw_response, request) {
                return parsed;
            }
            return self.safe_fallback(request, "invalid-response-fallback");
        }
        self.rule_based_fallback(request, &personality, "local-safe-policy")
    }

    fn build_prompt(&self, request: &JsonMap, personality: &Personality) -> String {
        let current_bet = as_i64(request.get("currentBet")).max(0);
        let committed_bet = as_i64(request.get("committedBet")).max(0);
        let to_call = (current_bet - committed_bet).max(0);
        format!(
            "Decide a single Texas Hold'em action for the current player.\n\n\
Constraints:\n\
- Return STRICT JSON object only.\n\
- Use one of legal actions exactly.\n\
- If action is BET or RAISE, amount must be total bet target for this round.\n\n\
JSON format:\n\
{{\"action\":\"FOLD|CHECK|CALL|BET|RAISE\",\"amount\":0,\"reason\":\"short text\"}}\n\n\
Context:\n\
tableId={}\n\
handNumber={}\n\
round={}\n\
playerId={}\n\
holeCards={:?}\n\
communityCards={:?}\n\
pot={}\n\
currentBet={}\n\
committed={}\n\
toCall={}\n\
stack={}\n\
minRaise={}\n\
legalActions={:?}\n\n\
Personality:\n\
type={}\n\
bluffFrequency={:.2}\n\
aggressionFactor={:.2}\n\
strategyHint={}",
            as_string(request.get("tableId")),
            as_i64(request.get("handNumber")),
            as_string(request.get("roundType")),
            as_string(request.get("playerId")),
            as_string_list(request.get("holeCards")),
            as_string_list(request.get("communityCards")),
            as_i64(request.get("pot")).max(0),
            current_bet,
            committed_bet,
            to_call,
            as_i64(request.get("stack")).max(0),
            as_i64(request.get("minRaise")).max(0),
            legal_action_list(request),
            personality.kind,
            personality.bluff_frequency,
            personality.aggression_factor,
            personality.strategy_hint
        )
    }

    fn generate_openai_decision(&self, prompt: &str) -> Option<String> {
        if prompt.trim().is_empty() {
            return None;
        }
        if self.config.llm_provider.trim().to_lowercase() != "openai" {
            return None;
        }
        let api_key = self.config.openai_api_key.clone()?;
        let body = json!({
            "model": if self.config.model.trim().is_empty() { "chatgpt-5.2-instant" } else { self.config.model.trim() },
            "max_output_tokens": 220,
            "text": { "verbosity": "low" },
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "You are a poker decision engine. Return strict JSON only."
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt
                        }
                    ]
                }
            ]
        });
        let response = self
            .http
            .post(OPENAI_RESPONSES_URL)
            .bearer_auth(api_key)
            .header("Content-Type", "application/json")
            .json(&body)
            .timeout(Duration::from_millis(self.config.action_timeout_millis))
            .send()
            .ok()?;
        if !response.status().is_success() {
            eprintln!(
                "OpenAI decision request failed with status {}",
                response.status().as_u16()
            );
            return None;
        }
        let payload = response.json::<Value>().ok()?;
        self.extract_output_text(&payload)
    }

    fn extract_output_text(&self, payload: &Value) -> Option<String> {
        if let Some(text) = payload.get("output_text").and_then(Value::as_str) {
            let trimmed = text.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }
        let output = payload.get("output").and_then(Value::as_array)?;
        let mut pieces: Vec<String> = Vec::new();
        for item in output {
            let Some(content) = item.get("content").and_then(Value::as_array) else {
                continue;
            };
            for piece in content {
                let Some(text) = piece.get("text").and_then(Value::as_str) else {
                    continue;
                };
                let trimmed = text.trim();
                if !trimmed.is_empty() {
                    pieces.push(trimmed.to_string());
                }
            }
        }
        if pieces.is_empty() {
            None
        } else {
            Some(pieces.join("\n"))
        }
    }

    fn parse_response(&self, raw_response: &str, request: &JsonMap) -> Option<JsonMap> {
        let mut trimmed = raw_response.trim().to_string();
        if trimmed.is_empty() {
            return None;
        }
        let start = trimmed.find('{');
        let end = trimmed.rfind('}');
        if let (Some(start_index), Some(end_index)) = (start, end) {
            if end_index > start_index {
                trimmed = trimmed[start_index..=end_index].to_string();
            }
        }
        let payload = serde_json::from_str::<Value>(&trimmed).ok()?;
        let payload_map = payload.as_object()?;
        let action_name = normalize_action_name(payload_map.get("action"))?;
        let amount = as_i64(payload_map.get("amount")).max(0);
        let reason = payload_map
            .get("reason")
            .and_then(Value::as_str)
            .map(|text| text.to_string());
        let action = action_map(&action_name, amount, reason);
        if !self.is_action_legal(&action, request) {
            return None;
        }
        Some(self.normalize_action(&action, request))
    }

    fn normalize_action(&self, action: &JsonMap, request: &JsonMap) -> JsonMap {
        let action_name = normalize_action_name(action.get("action")).unwrap_or_else(|| "FOLD".to_string());
        let current_bet = as_i64(request.get("currentBet")).max(0);
        let committed_bet = as_i64(request.get("committedBet")).max(0);
        let min_raise = as_i64(request.get("minRaise")).max(0);
        let stack = as_i64(request.get("stack")).max(0);
        let to_call = (current_bet - committed_bet).max(0);
        let amount = as_i64(action.get("amount")).max(0);
        let reason = action
            .get("reason")
            .and_then(Value::as_str)
            .map(|text| text.to_string());

        match action_name.as_str() {
            "FOLD" | "CHECK" => action_map(&action_name, 0, reason),
            "CALL" => action_map(&action_name, to_call.min(stack), reason),
            "BET" => {
                let min_target = min_raise.max(1);
                let max_target = committed_bet + stack;
                action_map(&action_name, amount.clamp(min_target, max_target), reason)
            }
            _ => {
                let min_target = current_bet + min_raise;
                let max_target = committed_bet + stack;
                action_map("RAISE", amount.clamp(min_target, max_target), reason)
            }
        }
    }

    fn is_action_legal(&self, action: &JsonMap, request: &JsonMap) -> bool {
        let legal_actions = legal_action_list(request);
        let Some(action_name) = normalize_action_name(action.get("action")) else {
            return false;
        };
        if !contains_action(&legal_actions, &action_name) {
            return false;
        }
        let current_bet = as_i64(request.get("currentBet")).max(0);
        let committed_bet = as_i64(request.get("committedBet")).max(0);
        let stack = as_i64(request.get("stack")).max(0);
        let to_call = (current_bet - committed_bet).max(0);
        match action_name.as_str() {
            "FOLD" => true,
            "CHECK" => to_call == 0,
            "CALL" => stack > 0,
            "BET" => current_bet == 0 && stack > 0,
            "RAISE" => current_bet > 0 && stack + committed_bet > current_bet,
            _ => false,
        }
    }

    fn rule_based_fallback(
        &self,
        request: &JsonMap,
        personality: &Personality,
        reason_tag: &str,
    ) -> JsonMap {
        let legal_actions = legal_action_list(request);
        let pot = as_i64(request.get("pot")).max(0);
        let current_bet = as_i64(request.get("currentBet")).max(0);
        let committed_bet = as_i64(request.get("committedBet")).max(0);
        let min_raise = as_i64(request.get("minRaise")).max(0);
        let stack = as_i64(request.get("stack")).max(0);
        let to_call = (current_bet - committed_bet).max(0);
        let aggressive = personality.aggression_factor >= 0.7;
        let bluffing = personality.bluff_frequency >= 0.3;

        if to_call == 0 {
            if contains_action(&legal_actions, "BET") && (aggressive || bluffing) {
                let target = (committed_bet + stack).min(min_raise.max(min_raise + pot / 6));
                return action_map("BET", target.max(0), Some(format!("{reason_tag}: pressure bet")));
            }
            return action_map("CHECK", 0, Some(format!("{reason_tag}: check")));
        }

        if contains_action(&legal_actions, "CALL") && aggressive && stack > to_call {
            return action_map(
                "CALL",
                to_call.min(stack),
                Some(format!("{reason_tag}: defend")),
            );
        }
        action_map("FOLD", 0, Some(format!("{reason_tag}: fold")))
    }

    fn safe_fallback(&self, request: &JsonMap, reason_tag: &str) -> JsonMap {
        let legal_actions = legal_action_list(request);
        let current_bet = as_i64(request.get("currentBet")).max(0);
        let committed_bet = as_i64(request.get("committedBet")).max(0);
        let stack = as_i64(request.get("stack")).max(0);
        let to_call = (current_bet - committed_bet).max(0);

        if to_call > 0 && contains_action(&legal_actions, "FOLD") {
            return action_map("FOLD", 0, Some(format!("{reason_tag}: fold")));
        }
        if contains_action(&legal_actions, "CHECK") {
            return action_map("CHECK", 0, Some(format!("{reason_tag}: check")));
        }
        if contains_action(&legal_actions, "CALL") {
            return action_map("CALL", to_call.min(stack), Some(format!("{reason_tag}: call")));
        }
        if let Some(first) = legal_actions.first() {
            return action_map(first, 0, Some(format!("{reason_tag}: fallback")));
        }
        action_map("FOLD", 0, Some(format!("{reason_tag}: fallback")))
    }
}

impl PokerRuntime {
    fn new(config: Config) -> Result<Self, String> {
        let mut options = AcpAgentOptions {
            storage_dir: config.acp_storage_dir.clone().into(),
            endpoint: Some(resolve_endpoint(&config.public_base_url, &config.acp_message_path)),
            discovery_scheme: config.acp_discovery_scheme.clone(),
            allow_insecure_http: config.acp_allow_insecure_http,
            allow_insecure_tls: config.acp_allow_insecure_tls,
            default_delivery_mode: config.acp_delivery_mode,
            ..AcpAgentOptions::default()
        };
        if let Some(ca_file) = &config.acp_ca_file {
            options.ca_file = Some(ca_file.clone());
        }
        if let Some(relay_url) = &config.acp_relay_url {
            options.relay_url = relay_url.clone();
            options.relay_hints = vec![relay_url.clone()];
        }
        let agent = AcpAgent::load_or_create(&config.local_agent_id, Some(options))
            .map_err(|error| format!("failed to load ACP agent: {error}"))?;
        let decision_engine = DecisionEngine::new(config.clone());
        Ok(Self {
            config,
            agent,
            decision_engine,
            sequence: 0,
            eliminated: false,
            active_table_id: None,
            last_hand_number: 0,
            hole_cards: Vec::new(),
        })
    }

    fn receive(&mut self, raw_message: &JsonMap) -> InboundResult {
        self.agent.receive(raw_message, None)
    }

    fn on_inbound_payload(&mut self, decrypted_payload: JsonMap) {
        let event = self.parse_inbound_event(&decrypted_payload);
        if event.event_type.is_empty() {
            return;
        }
        match event.event_type.as_str() {
            "INVITATION" => {
                let response = self.on_invitation(&event.payload);
                self.send_to_dealer(
                    "JOIN_TABLE",
                    event.table_id.clone(),
                    event.hand_number,
                    as_string(response.get("playerId")),
                    response,
                );
            }
            "HAND_START" => {
                let state = event.payload.get("state").and_then(Value::as_object);
                self.last_hand_number = as_i64(state.and_then(|entry| entry.get("handNumber")));
                println!(
                    "{} received HAND_START for hand {}",
                    self.config.player_id, self.last_hand_number
                );
            }
            "HOLE_CARDS" => {
                self.hole_cards = as_string_list(event.payload.get("holeCards"));
                println!(
                    "{} received hole cards {:?}",
                    self.config.player_id, self.hole_cards
                );
            }
            "ACTION_REQUEST" => {
                let response = self.on_action_request(&event.payload);
                self.send_to_dealer(
                    "ACTION_RESPONSE",
                    event.table_id.clone(),
                    event.hand_number,
                    as_string(response.get("playerId")),
                    response,
                );
            }
            "ACTION_APPLIED" => println!(
                "{} observed action {:?}",
                self.config.player_id,
                event.payload.get("action")
            ),
            "COMMUNITY_CARDS_UPDATED" => println!(
                "{} observed community cards {:?}",
                self.config.player_id,
                event.payload.get("communityCards")
            ),
            "HAND_RESULT" => println!(
                "{} received hand result winners={:?} payouts={:?}",
                self.config.player_id,
                event.payload.get("winnerIds"),
                event.payload.get("amountWonByPlayer")
            ),
            "PLAYER_ELIMINATED" => {
                if as_string(event.payload.get("playerId")) == self.config.player_id {
                    self.eliminated = true;
                    println!("{} has been eliminated", self.config.player_id);
                }
            }
            "GAME_FINISHED" => println!(
                "{} received GAME_FINISHED winner={:?} finalStacks={:?}",
                self.config.player_id,
                event.payload.get("winnerId"),
                event.payload.get("finalStacks")
            ),
            _ => {}
        }
    }

    fn get_well_known_document(&mut self) -> Result<JsonMap, String> {
        self.agent
            .build_well_known_document(Some(&self.config.public_base_url), None)
            .map_err(|error| format!("failed to build well-known document: {error}"))
    }

    fn get_identity_payload(&self) -> JsonMap {
        let mut payload = JsonMap::new();
        payload.insert(
            "identity_document".to_string(),
            Value::Object(self.agent.identity_document.clone()),
        );
        payload
    }

    fn on_invitation(&mut self, message: &JsonMap) -> JsonMap {
        let expected_player_id = as_string(message.get("playerId"));
        let accepted = expected_player_id == self.config.player_id;
        println!(
            "{} received INVITATION table={} seat={} expectedPlayerId='{}' accepted={}",
            self.config.player_id,
            as_string(message.get("tableId")),
            as_i64(message.get("seatNumber")),
            expected_player_id,
            accepted
        );
        if accepted {
            self.active_table_id = Some(as_string(message.get("tableId")));
            self.eliminated = false;
        }
        let mut response = JsonMap::new();
        response.insert("type".to_string(), Value::String("JOIN_TABLE".to_string()));
        response.insert(
            "tableId".to_string(),
            message.get("tableId").cloned().unwrap_or(Value::Null),
        );
        response.insert(
            "playerId".to_string(),
            Value::String(self.config.player_id.clone()),
        );
        response.insert(
            "seatNumber".to_string(),
            Value::from(as_i64(message.get("seatNumber")).max(1)),
        );
        response.insert("accepted".to_string(), Value::Bool(accepted));
        response.insert(
            "message".to_string(),
            Value::String(if accepted {
                "joined".to_string()
            } else {
                "player id mismatch".to_string()
            }),
        );
        response
    }

    fn on_action_request(&mut self, message: &JsonMap) -> JsonMap {
        let action = if self.eliminated {
            action_map("FOLD", 0, Some("eliminated".to_string()))
        } else {
            self.decision_engine.decide_action(message)
        };
        let mut response = JsonMap::new();
        response.insert(
            "type".to_string(),
            Value::String("ACTION_RESPONSE".to_string()),
        );
        response.insert(
            "tableId".to_string(),
            message.get("tableId").cloned().unwrap_or(Value::Null),
        );
        response.insert(
            "playerId".to_string(),
            Value::String(self.config.player_id.clone()),
        );
        response.insert("action".to_string(), Value::Object(action));
        response
    }

    fn send_to_dealer(
        &mut self,
        message_type: &str,
        table_id: Option<String>,
        hand_number: Option<i64>,
        player_id: String,
        payload: JsonMap,
    ) {
        let encoded = self.encode_payload(
            message_type,
            table_id.clone(),
            hand_number,
            player_id,
            payload,
        );
        let context = format!("poker:{}", table_id.clone().unwrap_or_else(|| "table".to_string()));
        match self.agent.send(
            vec![self.config.dealer_agent_id.clone()],
            encoded,
            Some(context),
            MessageClass::Send,
            300,
            None,
            None,
            Some(self.config.acp_delivery_mode),
        ) {
            Ok(result) => {
                if !is_delivered(&result) {
                    println!(
                        "ACP send failed from {} to dealer: {}",
                        self.config.player_id,
                        summarize_failure(&result)
                    );
                }
            }
            Err(error) => println!(
                "ACP send failed from {} to dealer: {}",
                self.config.player_id, error
            ),
        }
    }

    fn encode_payload(
        &mut self,
        message_type: &str,
        table_id: Option<String>,
        hand_number: Option<i64>,
        player_id: String,
        payload: JsonMap,
    ) -> JsonMap {
        self.sequence += 1;
        let mut event = JsonMap::new();
        event.insert("profile".to_string(), Value::String(POKER_PROFILE.to_string()));
        event.insert(
            "table_id".to_string(),
            table_id
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        event.insert(
            "hand_number".to_string(),
            hand_number.map(Value::from).unwrap_or(Value::Null),
        );
        event.insert("sequence".to_string(), Value::from(self.sequence));
        event.insert(
            "event_type".to_string(),
            Value::String(message_type.to_string()),
        );
        event.insert(
            "player_id".to_string(),
            Value::String(if player_id.trim().is_empty() {
                self.config.player_id.clone()
            } else {
                player_id
            }),
        );
        event.insert(
            "sent_at".to_string(),
            Value::String(Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)),
        );
        event.insert("payload".to_string(), Value::Object(payload));
        event
    }

    fn parse_inbound_event(&self, payload: &JsonMap) -> InboundEvent {
        if as_string(payload.get("profile")) == POKER_PROFILE
            && payload.get("event_type").and_then(Value::as_str).is_some()
            && payload.get("payload").and_then(Value::as_object).is_some()
        {
            let body = payload
                .get("payload")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            let table_id = first_non_blank(&[
                Some(as_string(payload.get("table_id"))),
                Some(as_string(body.get("tableId"))),
            ]);
            let hand_number = if payload.get("hand_number").is_some() {
                Some(as_i64(payload.get("hand_number")))
            } else if body.get("handNumber").is_some() {
                Some(as_i64(body.get("handNumber")))
            } else {
                None
            };
            return InboundEvent {
                event_type: as_string(payload.get("event_type")).to_uppercase(),
                table_id,
                hand_number,
                payload: body,
            };
        }

        InboundEvent {
            event_type: as_string(payload.get("type")).to_uppercase(),
            table_id: Some(as_string(payload.get("tableId"))).filter(|value| !value.is_empty()),
            hand_number: payload.get("handNumber").map(|value| as_i64(Some(value))),
            payload: payload.clone(),
        }
    }
}

fn is_delivered(result: &SendResult) -> bool {
    result.outcomes.iter().any(|outcome| {
        outcome.state == DeliveryState::Acknowledged || outcome.state == DeliveryState::Delivered
    })
}

fn summarize_failure(result: &SendResult) -> String {
    let Some(first) = result.outcomes.first() else {
        return "no delivery outcomes".to_string();
    };
    format!(
        "state={:?}, reasonCode={:?}, detail={:?}",
        first.state, first.reason_code, first.detail
    )
}

fn run_inbound_worker(mut runtime: PokerRuntime, inbound_rx: mpsc::Receiver<JsonMap>) {
    for raw_payload in inbound_rx {
        let started = Instant::now();
        let inbound = runtime.receive(&raw_payload);
        let elapsed_ms = started.elapsed().as_millis();

        let envelope = raw_payload.get("envelope").and_then(Value::as_object);
        let message_id = as_string(envelope.and_then(|value| value.get("message_id")));
        let sender_id = as_string(envelope.and_then(|value| value.get("sender")));
        let message_class =
            as_string(envelope.and_then(|value| value.get("message_class"))).to_uppercase();
        println!(
            "{} ACP inbound messageId={} sender={} class={} state={:?} reason={:?} detail={} decrypted={} elapsedMs={}",
            runtime.config.player_id,
            message_id,
            sender_id,
            message_class,
            inbound.state,
            inbound.reason_code,
            inbound.detail.as_deref().unwrap_or(""),
            inbound.decrypted_payload.is_some(),
            elapsed_ms
        );

        if let Some(payload) = inbound.decrypted_payload {
            runtime.on_inbound_payload(payload);
        }
    }
}

fn handle_request(server_state: &ServerState, mut request: Request) {
    let method = request.method().clone();
    let path = request
        .url()
        .split('?')
        .next()
        .map(str::to_string)
        .unwrap_or_else(|| "/".to_string());

    match (method, path.as_str()) {
        (Method::Get, "/.well-known/acp") => respond_json(
            request,
            StatusCode(200),
            Value::Object(server_state.well_known_document.clone()),
        ),
        (Method::Get, "/api/v1/acp/identity") => respond_json(
            request,
            StatusCode(200),
            Value::Object(server_state.identity_payload.clone()),
        ),
        (Method::Post, "/api/v1/acp/messages") => {
            let raw_payload = match read_json_map(&mut request) {
                Ok(payload) => payload,
                Err(error) => {
                    respond_json(
                        request,
                        StatusCode(400),
                        json!({ "error": error }),
                    );
                    return;
                }
            };

            if let Err(error) = server_state.inbound_tx.send(raw_payload) {
                respond_json(
                    request,
                    StatusCode(500),
                    json!({
                        "state": "FAILED",
                        "reason_code": "POLICY_REJECTED",
                        "detail": format!("inbound worker unavailable: {error}"),
                        "decrypted_payload": null,
                        "response_message": null
                    }),
                );
                return;
            }

            respond_json(
                request,
                StatusCode(200),
                json!({
                    "state": "ACKNOWLEDGED",
                    "reason_code": null,
                    "detail": "accepted for async processing",
                    "decrypted_payload": null,
                    "response_message": null
                }),
            );
        }
        _ => respond_json(
            request,
            StatusCode(404),
            json!({ "error": "not found" }),
        ),
    }
}

fn read_json_map(request: &mut Request) -> Result<JsonMap, String> {
    let mut deserializer = serde_json::Deserializer::from_reader(request.as_reader());
    let parsed = match Value::deserialize(&mut deserializer) {
        Ok(parsed) => parsed,
        Err(error) if error.is_eof() => return Ok(JsonMap::new()),
        Err(error) => return Err(format!("invalid json payload: {error}")),
    };
    parsed
        .as_object()
        .cloned()
        .ok_or_else(|| "payload must be a JSON object".to_string())
}

fn respond_json(request: Request, status: StatusCode, body: Value) {
    let payload = serde_json::to_string(&body).unwrap_or_else(|_| "{}".to_string());
    let response = Response::from_string(payload)
        .with_status_code(status)
        .with_header(
            Header::from_bytes("Content-Type", "application/json")
                .unwrap_or_else(|_| Header::from_bytes("Content-Type", "application/json").expect("header")),
        );
    if let Err(error) = request.respond(response) {
        eprintln!("failed to send response: {error}");
    }
}
