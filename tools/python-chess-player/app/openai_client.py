from __future__ import annotations

import logging
import re
from typing import Iterable

import requests

from .config import AppConfig
from .models import ChessColor, ReasoningEffort


LOG = logging.getLogger(__name__)
_UCI_MOVE_PATTERN = re.compile(r"([a-h][1-8][a-h][1-8][qrbn]?)")


class OpenAiChessMoveClient:
    RESPONSES_API_URL = "https://api.openai.com/v1/responses"

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def choose_move(
        self,
        *,
        fen: str,
        side_to_play: ChessColor,
        legal_moves_uci: list[str],
        reasoning_effort: ReasoningEffort,
    ) -> str | None:
        api_key = (self._config.openai_api_key or "").strip()
        if not api_key or not legal_moves_uci:
            return None

        legal_set = {move.strip().lower() for move in legal_moves_uci if move and move.strip()}
        if not legal_set:
            return None

        payload = self._build_payload(fen, side_to_play, legal_moves_uci, reasoning_effort)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                self.RESPONSES_API_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
            if response.status_code < 200 or response.status_code >= 300:
                LOG.warning("OpenAI move request rejected with status %s", response.status_code)
                return None
            raw_text = self._extract_output_text(response.json())
            if not raw_text:
                return None
            return self._select_legal_move(raw_text, legal_set)
        except Exception:
            LOG.exception("OpenAI move request failed")
            return None

    def _build_payload(
        self,
        fen: str,
        side_to_play: ChessColor,
        legal_moves_uci: list[str],
        reasoning_effort: ReasoningEffort,
    ) -> dict[str, object]:
        model = self._resolve_model(self._config.openai_model)
        system_prompt = (
            "You are a chess engine assistant.\n"
            "Return exactly one legal move in UCI format.\n"
            "Choose from the legal moves list only.\n"
            "Return only the move text and nothing else."
        )
        user_prompt = (
            f"FEN: {fen}\n"
            f"Side to move: {side_to_play.value.lower()}\n"
            f"Legal moves (UCI): {' '.join(legal_moves_uci)}"
        )
        return {
            "model": model,
            "max_output_tokens": 24,
            "reasoning": {"effort": reasoning_effort.api_value()},
            "text": {"verbosity": "low"},
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
        }

    @staticmethod
    def _select_legal_move(raw_text: str, legal_moves: set[str]) -> str | None:
        normalized = raw_text.strip().lower()
        if normalized in legal_moves:
            return normalized
        for match in _UCI_MOVE_PATTERN.findall(normalized):
            if match in legal_moves:
                return match
        return None

    @staticmethod
    def _extract_output_text(response_json: dict[str, object]) -> str | None:
        output_text = response_json.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        if isinstance(output_text, list):
            text = "\n".join(item.strip() for item in output_text if isinstance(item, str) and item.strip())
            if text:
                return text

        output = response_json.get("output")
        if not isinstance(output, list):
            return None
        lines: list[str] = []
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
                    lines.append(text.strip())
        if not lines:
            return None
        return "\n".join(lines)

    @staticmethod
    def _resolve_model(configured_model: str | None) -> str:
        if not configured_model or not configured_model.strip():
            return "o3-mini"
        normalized = re.sub(r"[^a-z0-9]", "", configured_model.strip().lower())
        if normalized == "chatgpt3minio":
            return "o3-mini"
        return configured_model.strip()

