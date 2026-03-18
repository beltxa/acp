#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from acp import Agent, DeliveryState
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    sdk_path = repo_root / "sdks" / "python"
    if sdk_path.exists():
        sys.path.insert(0, str(sdk_path))
    from acp import Agent, DeliveryState


LOG = logging.getLogger("poker-python-player")
POKER_PROFILE = "UCW_POKER_V1"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
LEGAL_ACTIONS = {"FOLD", "CHECK", "CALL", "BET", "RAISE"}


@dataclass(frozen=True)
class Personality:
    type: str
    bluff_frequency: float
    aggression_factor: float
    strategy_hint: str


PERSONALITY_MAP: dict[str, Personality] = {
    "TIGHT_AGGRESSIVE": Personality(
        type="TIGHT_AGGRESSIVE",
        bluff_frequency=0.10,
        aggression_factor=0.78,
        strategy_hint="Play strong ranges and pressure with value-heavy raises.",
    ),
    "LOOSE_AGGRESSIVE": Personality(
        type="LOOSE_AGGRESSIVE",
        bluff_frequency=0.25,
        aggression_factor=0.88,
        strategy_hint="Contest many pots and apply pressure often.",
    ),
    "CONSERVATIVE": Personality(
        type="CONSERVATIVE",
        bluff_frequency=0.05,
        aggression_factor=0.35,
        strategy_hint="Avoid marginal spots and preserve stack.",
    ),
    "CHAOTIC": Personality(
        type="CHAOTIC",
        bluff_frequency=0.45,
        aggression_factor=0.92,
        strategy_hint="Mix in unpredictable aggression and occasional bluffs.",
    ),
}


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except Exception:
            return default
    return default


def to_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized = item.strip()
            if normalized:
                output.append(normalized)
    return output


def normalize_action_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().upper()
    return normalized if normalized in LEGAL_ACTIONS else ""


@dataclass
class PlayerConfig:
    server_port: int
    player_id: str
    entity_id: str
    personality: str
    llm_provider: str
    model: str
    local_agent_id: str
    dealer_agent_id: str
    public_base_url: str
    acp_message_path: str
    acp_storage_dir: str
    acp_discovery_scheme: str
    acp_relay_url: str | None
    acp_allow_insecure_http: bool
    acp_allow_insecure_tls: bool
    acp_ca_file: str | None
    acp_delivery_mode: str
    action_timeout_millis: int
    openai_api_key: str | None

    @classmethod
    def from_env(cls) -> "PlayerConfig":
        return cls(
            server_port=to_int(os.getenv("SERVER_PORT"), 8091),
            player_id=os.getenv("POKER_PLAYER_PLAYER_ID", "Player-1"),
            entity_id=os.getenv("POKER_PLAYER_ENTITY_ID", "Entity-A"),
            personality=os.getenv("POKER_PLAYER_PERSONALITY", "TIGHT_AGGRESSIVE"),
            llm_provider=os.getenv("POKER_PLAYER_LLM_PROVIDER", "openai"),
            model=os.getenv("POKER_PLAYER_MODEL", "chatgpt-5.2-instant"),
            local_agent_id=os.getenv("POKER_PLAYER_LOCAL_AGENT_ID", "agent:player1@localhost:8091"),
            dealer_agent_id=os.getenv("POKER_PLAYER_DEALER_AGENT_ID", "agent:dealer@localhost:8090"),
            public_base_url=os.getenv("POKER_PLAYER_PUBLIC_BASE_URL", "http://localhost:8091"),
            acp_message_path=os.getenv("POKER_PLAYER_ACP_MESSAGE_PATH", "/api/v1/acp/messages"),
            acp_storage_dir=os.getenv("POKER_PLAYER_ACP_STORAGE_DIR", "/var/lib/poker-player/acp"),
            acp_discovery_scheme=os.getenv("POKER_PLAYER_ACP_DISCOVERY_SCHEME", "http"),
            acp_relay_url=(os.getenv("POKER_PLAYER_ACP_RELAY_URL") or "").strip() or None,
            acp_allow_insecure_http=parse_bool(os.getenv("POKER_PLAYER_ACP_ALLOW_INSECURE_HTTP"), False),
            acp_allow_insecure_tls=parse_bool(os.getenv("POKER_PLAYER_ACP_ALLOW_INSECURE_TLS"), False),
            acp_ca_file=(os.getenv("POKER_PLAYER_ACP_CA_FILE") or "").strip() or None,
            acp_delivery_mode=os.getenv("POKER_PLAYER_ACP_DELIVERY_MODE", "direct"),
            action_timeout_millis=max(1000, to_int(os.getenv("POKER_PLAYER_ACTION_TIMEOUT_MILLIS"), 12000)),
            openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip() or None,
        )

    def resolve_endpoint(self) -> str:
        base = self.public_base_url.rstrip("/")
        path = self.acp_message_path if self.acp_message_path.startswith("/") else f"/{self.acp_message_path}"
        return f"{base}{path}"

    def resolve_delivery_mode(self) -> str:
        normalized = (self.acp_delivery_mode or "direct").strip().lower()
        return normalized if normalized in {"auto", "direct", "relay", "amqp", "mqtt"} else "direct"


def personality_for(config: PlayerConfig) -> Personality:
    configured = (config.personality or "").strip().upper()
    if configured in PERSONALITY_MAP:
        return PERSONALITY_MAP[configured]
    if config.player_id.lower() == "player-1":
        return PERSONALITY_MAP["TIGHT_AGGRESSIVE"]
    if config.player_id.lower() == "player-2":
        return PERSONALITY_MAP["LOOSE_AGGRESSIVE"]
    if config.player_id.lower() == "player-3":
        return PERSONALITY_MAP["CONSERVATIVE"]
    return PERSONALITY_MAP["CHAOTIC"]


class DecisionEngine:
    def __init__(self, config: PlayerConfig) -> None:
        self.config = config

    def decide_action(self, request: dict[str, Any]) -> dict[str, Any]:
        personality = personality_for(self.config)
        prompt = self.build_prompt(request, personality)
        raw_response = self._generate_openai_decision(prompt)
        if raw_response:
            parsed = self._parse_response(raw_response, request)
            if parsed is not None:
                return parsed
            return self._safe_fallback(request, "invalid-response-fallback")
        return self._rule_based_fallback(request, personality, "local-safe-policy")

    def build_prompt(self, request: dict[str, Any], personality: Personality) -> str:
        current_bet = max(0, to_int(request.get("currentBet")))
        committed_bet = max(0, to_int(request.get("committedBet")))
        to_call = max(0, current_bet - committed_bet)
        return f"""
Decide a single Texas Hold'em action for the current player.

Constraints:
- Return STRICT JSON object only.
- Use one of legal actions exactly.
- If action is BET or RAISE, amount must be total bet target for this round.

JSON format:
{{"action":"FOLD|CHECK|CALL|BET|RAISE","amount":0,"reason":"short text"}}

Context:
tableId={request.get("tableId")}
handNumber={to_int(request.get("handNumber"))}
round={request.get("roundType")}
playerId={request.get("playerId")}
holeCards={to_string_list(request.get("holeCards"))}
communityCards={to_string_list(request.get("communityCards"))}
pot={max(0, to_int(request.get("pot")))}
currentBet={current_bet}
committed={committed_bet}
toCall={to_call}
stack={max(0, to_int(request.get("stack")))}
minRaise={max(0, to_int(request.get("minRaise")))}
legalActions={self._legal_actions(request)}

Personality:
type={personality.type}
bluffFrequency={personality.bluff_frequency:.2f}
aggressionFactor={personality.aggression_factor:.2f}
strategyHint={personality.strategy_hint}
""".strip()

    def _generate_openai_decision(self, prompt: str) -> str | None:
        if not prompt.strip():
            return None
        if self.config.llm_provider.strip().lower() != "openai":
            return None
        api_key = self.config.openai_api_key
        if not api_key:
            return None

        body = {
            "model": self.config.model or "chatgpt-5.2-instant",
            "max_output_tokens": 220,
            "text": {"verbosity": "low"},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "You are a poker decision engine. Return strict JSON only.",
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                },
            ],
        }
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout_seconds = max(1, self.config.action_timeout_millis / 1000)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    LOG.warning("OpenAI decision request failed with status %s", response.status)
                    return None
                payload = json.loads(response.read().decode("utf-8"))
                return self._extract_output_text(payload)
        except urllib.error.HTTPError as exc:
            LOG.warning("OpenAI decision request failed with status %s", exc.code)
            return None
        except Exception:
            LOG.warning("OpenAI decision request failed", exc_info=True)
            return None

    def _extract_output_text(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        output = payload.get("output")
        if not isinstance(output, list):
            return None
        pieces: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    pieces.append(text.strip())
        if not pieces:
            return None
        return "\n".join(pieces)

    def _parse_response(self, raw_response: str, request: dict[str, Any]) -> dict[str, Any] | None:
        if not raw_response.strip():
            return None
        text = raw_response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            payload = json.loads(text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        action_name = normalize_action_name(payload.get("action"))
        if not action_name:
            return None
        action = {
            "action": action_name,
            "amount": max(0, to_int(payload.get("amount"))),
            "reason": payload.get("reason") if isinstance(payload.get("reason"), str) else None,
        }
        if not self._is_action_legal(action, request):
            return None
        return self._normalize_action(action, request)

    def _normalize_action(self, action: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        action_name = normalize_action_name(action.get("action"))
        reason = action.get("reason")
        current_bet = max(0, to_int(request.get("currentBet")))
        committed_bet = max(0, to_int(request.get("committedBet")))
        min_raise = max(0, to_int(request.get("minRaise")))
        stack = max(0, to_int(request.get("stack")))
        to_call = max(0, current_bet - committed_bet)
        amount = max(0, to_int(action.get("amount")))

        if action_name in {"FOLD", "CHECK"}:
            return {"action": action_name, "amount": 0, "reason": reason}
        if action_name == "CALL":
            return {"action": action_name, "amount": min(to_call, stack), "reason": reason}
        if action_name == "BET":
            min_target = max(min_raise, 1)
            max_target = committed_bet + stack
            return {"action": action_name, "amount": max(min_target, min(amount, max_target)), "reason": reason}
        min_target = current_bet + min_raise
        max_target = committed_bet + stack
        return {"action": action_name, "amount": max(min_target, min(amount, max_target)), "reason": reason}

    def _is_action_legal(self, action: dict[str, Any], request: dict[str, Any]) -> bool:
        legal = self._legal_actions(request)
        action_name = normalize_action_name(action.get("action"))
        if action_name not in legal:
            return False
        current_bet = max(0, to_int(request.get("currentBet")))
        committed_bet = max(0, to_int(request.get("committedBet")))
        stack = max(0, to_int(request.get("stack")))
        to_call = max(0, current_bet - committed_bet)
        if action_name == "FOLD":
            return True
        if action_name == "CHECK":
            return to_call == 0
        if action_name == "CALL":
            return stack > 0
        if action_name == "BET":
            return current_bet == 0 and stack > 0
        return current_bet > 0 and stack + committed_bet > current_bet

    def _rule_based_fallback(
        self,
        request: dict[str, Any],
        personality: Personality,
        reason_tag: str,
    ) -> dict[str, Any]:
        legal = self._legal_actions(request)
        pot = max(0, to_int(request.get("pot")))
        current_bet = max(0, to_int(request.get("currentBet")))
        committed_bet = max(0, to_int(request.get("committedBet")))
        min_raise = max(0, to_int(request.get("minRaise")))
        stack = max(0, to_int(request.get("stack")))
        to_call = max(0, current_bet - committed_bet)
        aggressive = personality.aggression_factor >= 0.7
        bluffing = personality.bluff_frequency >= 0.3

        if to_call == 0:
            if "BET" in legal and (aggressive or bluffing):
                target = min(committed_bet + stack, max(min_raise, min_raise + pot // 6))
                return {"action": "BET", "amount": max(0, target), "reason": f"{reason_tag}: pressure bet"}
            return {"action": "CHECK", "amount": 0, "reason": f"{reason_tag}: check"}

        if "CALL" in legal and aggressive and stack > to_call:
            return {"action": "CALL", "amount": min(to_call, stack), "reason": f"{reason_tag}: defend"}

        return {"action": "FOLD", "amount": 0, "reason": f"{reason_tag}: fold"}

    def _safe_fallback(self, request: dict[str, Any], reason_tag: str) -> dict[str, Any]:
        legal = self._legal_actions(request)
        current_bet = max(0, to_int(request.get("currentBet")))
        committed_bet = max(0, to_int(request.get("committedBet")))
        stack = max(0, to_int(request.get("stack")))
        to_call = max(0, current_bet - committed_bet)

        if to_call > 0 and "FOLD" in legal:
            return {"action": "FOLD", "amount": 0, "reason": f"{reason_tag}: fold"}
        if "CHECK" in legal:
            return {"action": "CHECK", "amount": 0, "reason": f"{reason_tag}: check"}
        if "CALL" in legal:
            return {"action": "CALL", "amount": min(to_call, stack), "reason": f"{reason_tag}: call"}
        if legal:
            return {"action": legal[0], "amount": 0, "reason": f"{reason_tag}: fallback"}
        return {"action": "FOLD", "amount": 0, "reason": f"{reason_tag}: fallback"}

    def _legal_actions(self, request: dict[str, Any]) -> list[str]:
        output: list[str] = []
        for action in to_string_list(request.get("legalActions")):
            normalized = normalize_action_name(action)
            if normalized:
                output.append(normalized)
        return output


class PokerPlayerRuntime:
    def __init__(self, config: PlayerConfig) -> None:
        self.config = config
        self.delivery_mode = config.resolve_delivery_mode()
        self.agent = self._build_agent()
        self.decision_engine = DecisionEngine(config)
        self.sequence = 0
        self.eliminated = False
        self.active_table_id: str | None = None
        self.last_hand_number = 0
        self.hole_cards: list[str] = []
        self._lock = threading.RLock()

    def receive(self, raw_message: dict[str, Any]) -> dict[str, Any]:
        return self.agent.handle_incoming(raw_message)

    def on_inbound_payload(self, decrypted_payload: dict[str, Any]) -> None:
        event_type, table_id, hand_number, body = self._parse_event(decrypted_payload)
        if not event_type or not isinstance(body, dict):
            return
        try:
            if event_type == "INVITATION":
                response = self._on_invitation(body)
                self._send_to_dealer("JOIN_TABLE", table_id, hand_number, response.get("playerId"), response)
                return
            if event_type == "HAND_START":
                self.last_hand_number = max(0, to_int(body.get("state", {}).get("handNumber")))
                LOG.info("%s received HAND_START for hand %s", self.config.player_id, self.last_hand_number)
                return
            if event_type == "HOLE_CARDS":
                self.hole_cards = to_string_list(body.get("holeCards"))
                LOG.info("%s received hole cards %s", self.config.player_id, self.hole_cards)
                return
            if event_type == "ACTION_REQUEST":
                response = self._on_action_request(body)
                self._send_to_dealer("ACTION_RESPONSE", table_id, hand_number, response.get("playerId"), response)
                return
            if event_type == "ACTION_APPLIED":
                LOG.debug("%s observed action %s", self.config.player_id, body.get("action"))
                return
            if event_type == "COMMUNITY_CARDS_UPDATED":
                LOG.debug("%s observed community cards %s", self.config.player_id, body.get("communityCards"))
                return
            if event_type == "HAND_RESULT":
                LOG.info(
                    "%s received hand result winners=%s payouts=%s",
                    self.config.player_id,
                    body.get("winnerIds"),
                    body.get("amountWonByPlayer"),
                )
                return
            if event_type == "PLAYER_ELIMINATED":
                if str(body.get("playerId")) == self.config.player_id:
                    self.eliminated = True
                    LOG.info("%s has been eliminated", self.config.player_id)
                return
            if event_type == "GAME_FINISHED":
                LOG.info(
                    "%s received GAME_FINISHED winner=%s finalStacks=%s",
                    self.config.player_id,
                    body.get("winnerId"),
                    body.get("finalStacks"),
                )
                return
        except Exception:
            LOG.warning("Failed to process inbound payload for %s", self.config.player_id, exc_info=True)

    def get_well_known_document(self) -> dict[str, Any]:
        return self.agent.build_well_known_document(base_url=self.config.public_base_url)

    def get_identity_document_payload(self) -> dict[str, Any]:
        return {"identity_document": self.agent.identity_document}

    def _on_invitation(self, message: dict[str, Any]) -> dict[str, Any]:
        expected_player_id = str(message.get("playerId") or "")
        accepted = self.config.player_id == expected_player_id
        LOG.info(
            "%s received INVITATION table=%s seat=%s expectedPlayerId=%r accepted=%s",
            self.config.player_id,
            message.get("tableId"),
            message.get("seatNumber"),
            expected_player_id,
            accepted,
        )
        if accepted:
            self.active_table_id = str(message.get("tableId") or "")
            self.eliminated = False
        return {
            "type": "JOIN_TABLE",
            "tableId": message.get("tableId"),
            "playerId": self.config.player_id,
            "seatNumber": max(1, to_int(message.get("seatNumber"), 1)),
            "accepted": accepted,
            "message": "joined" if accepted else "player id mismatch",
        }

    def _on_action_request(self, message: dict[str, Any]) -> dict[str, Any]:
        if self.eliminated:
            action = {"action": "FOLD", "amount": 0, "reason": "eliminated"}
        else:
            action = self.decision_engine.decide_action(message)
        return {
            "type": "ACTION_RESPONSE",
            "tableId": message.get("tableId"),
            "playerId": self.config.player_id,
            "action": action,
        }

    def _send_to_dealer(
        self,
        message_type: str,
        table_id: str | None,
        hand_number: int | None,
        player_id: Any,
        payload: dict[str, Any],
    ) -> None:
        encoded = self._encode_payload(message_type, table_id, hand_number, player_id, payload)
        result = self.agent.send(
            recipients=[self.config.dealer_agent_id],
            payload=encoded,
            context=f"poker:{table_id or 'table'}",
            delivery_mode=self.delivery_mode,
        )
        if self._is_delivered(result):
            return
        LOG.warning("ACP send failed from %s to dealer: %s", self.config.player_id, self._summarize_failure(result))

    def _encode_payload(
        self,
        message_type: str,
        table_id: str | None,
        hand_number: int | None,
        player_id: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self.sequence += 1
            sequence = self.sequence
        return {
            "profile": POKER_PROFILE,
            "table_id": table_id,
            "hand_number": hand_number if hand_number is not None else None,
            "sequence": sequence,
            "event_type": message_type,
            "player_id": str(player_id) if player_id is not None else self.config.player_id,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

    def _parse_event(self, payload: dict[str, Any]) -> tuple[str, str | None, int | None, dict[str, Any]]:
        if (
            payload.get("profile") == POKER_PROFILE
            and isinstance(payload.get("event_type"), str)
            and isinstance(payload.get("payload"), dict)
        ):
            table_id = payload.get("table_id")
            hand_number_raw = payload.get("hand_number")
            hand_number = to_int(hand_number_raw) if hand_number_raw is not None else None
            return (
                str(payload.get("event_type")).strip().upper(),
                str(table_id) if table_id is not None else None,
                hand_number,
                dict(payload.get("payload")),
            )

        event_type = str(payload.get("type") or "").strip().upper()
        table_id_raw = payload.get("tableId")
        table_id = str(table_id_raw) if table_id_raw is not None else None
        hand_number_raw = payload.get("handNumber")
        hand_number = to_int(hand_number_raw) if hand_number_raw is not None else None
        return event_type, table_id, hand_number, payload

    @staticmethod
    def _is_delivered(result: Any) -> bool:
        outcomes = getattr(result, "outcomes", None) or []
        for outcome in outcomes:
            state = getattr(outcome, "state", None)
            if state in {DeliveryState.ACKNOWLEDGED, DeliveryState.DELIVERED, "ACKNOWLEDGED", "DELIVERED"}:
                return True
            value = getattr(state, "value", None)
            if value in {"ACKNOWLEDGED", "DELIVERED"}:
                return True
        return False

    @staticmethod
    def _summarize_failure(result: Any) -> str:
        outcomes = getattr(result, "outcomes", None) or []
        if not outcomes:
            return "no delivery outcomes"
        first = outcomes[0]
        state = getattr(first, "state", None)
        state_value = getattr(state, "value", state)
        return f"state={state_value}, reasonCode={getattr(first, 'reason_code', None)}, detail={getattr(first, 'detail', None)}"

    def _build_agent(self) -> Agent:
        kwargs: dict[str, Any] = {
            "storage_dir": self.config.acp_storage_dir,
            "endpoint": self.config.resolve_endpoint(),
            "discovery_scheme": self.config.acp_discovery_scheme,
            "allow_insecure_http": self.config.acp_allow_insecure_http,
            "allow_insecure_tls": self.config.acp_allow_insecure_tls,
            "ca_file": self.config.acp_ca_file,
        }
        if self.config.acp_relay_url:
            kwargs["relay_url"] = self.config.acp_relay_url
            kwargs["relay_hints"] = [self.config.acp_relay_url]
        return Agent.load_or_create(self.config.local_agent_id, **kwargs)


class RequestHandler(BaseHTTPRequestHandler):
    runtime: PokerPlayerRuntime

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/.well-known/acp":
            self._write_json(200, self.runtime.get_well_known_document())
            return
        if path == "/api/v1/acp/identity":
            self._write_json(200, self.runtime.get_identity_document_payload())
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path != "/api/v1/acp/messages":
            self._write_json(404, {"error": "not found"})
            return
        length = to_int(self.headers.get("Content-Length"), 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") if raw else "{}")
        except Exception:
            self._write_json(400, {"error": "invalid json payload"})
            return
        if not isinstance(payload, dict):
            self._write_json(400, {"error": "payload must be a JSON object"})
            return

        envelope = payload.get("envelope")
        LOG.debug("ACP inbound raw payload=%s", json.dumps(payload, sort_keys=True, separators=(",", ":")))
        if isinstance(envelope, dict):
            LOG.debug(
                "ACP inbound envelope messageId=%s sender=%s correlation_id=%r in_reply_to=%r recipientCount=%s",
                envelope.get("message_id"),
                envelope.get("sender"),
                envelope.get("correlation_id"),
                envelope.get("in_reply_to"),
                len(envelope.get("recipients", [])) if isinstance(envelope.get("recipients"), list) else 0,
            )

        inbound = self.runtime.receive(payload)
        if inbound.get("state") == "FAILED":
            LOG.warning(
                "ACP inbound failed messageId=%s reason=%s detail=%s",
                envelope.get("message_id") if isinstance(envelope, dict) else None,
                inbound.get("reason_code"),
                inbound.get("detail"),
            )
        decrypted_payload = inbound.get("decrypted_payload")
        if isinstance(decrypted_payload, dict):
            self.runtime.on_inbound_payload(decrypted_payload)
        self._write_json(200, inbound)

    def log_message(self, format: str, *args: Any) -> None:
        LOG.debug("%s - %s", self.address_string(), format % args)

    def _write_json(self, status_code: int, body: Any) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    config = PlayerConfig.from_env()
    runtime = PokerPlayerRuntime(config)
    RequestHandler.runtime = runtime

    LOG.info(
        "Player %s (%s) started with provider=%s model=%s personality=%s localAgentId=%s",
        config.player_id,
        config.entity_id,
        config.llm_provider,
        config.model,
        config.personality,
        config.local_agent_id,
    )
    server = ThreadingHTTPServer(("0.0.0.0", config.server_port), RequestHandler)
    LOG.info("Python poker player listening on 0.0.0.0:%s", config.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
