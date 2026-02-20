from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import chess

from .base import MoveResult, PlayerAdapter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a chess grandmaster competing in a tournament.
Given the current board position (FEN notation) and the list of legal moves
available to you, choose the best move.

Rules:
- Respond with ONLY a single UCI-format move (e.g. \"e2e4\", \"g1f3\", \"e7e8q\")
- No explanations, no commentary, no formatting - just the move string
- The move MUST be from the legal moves list provided
- Do NOT include thinking or reasoning text"""
# Keep a large floor so models that spend tokens on hidden reasoning still emit a move.
MIN_REASONING_SAFE_MAX_TOKENS = 1024
_SAN_CANDIDATE_RE = re.compile(
    r"\b(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b",
    flags=re.IGNORECASE,
)
_UCI_CANDIDATE_RE = re.compile(r"\b([a-h][1-8]\s*[a-h][1-8]\s*[qrbn]?)\b", flags=re.IGNORECASE)


@dataclass
class _ApiResult:
    text: str
    tokens: int
    cost_usd: float


class LLMPlayer(PlayerAdapter):
    def __init__(
        self,
        name: str,
        provider: str,
        model: str,
        api_key: str,
        max_retries: int = 5,
        temperature: float = 0.0,
        max_tokens: int = MIN_REASONING_SAFE_MAX_TOKENS,
        base_url: str = "https://openrouter.ai/api/v1",
        http_referer: str = "",
        x_title: str = "ChessBench",
        reasoning_effort: str | None = None,
    ) -> None:
        self.name = name
        self.provider = provider.strip().lower()
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.http_referer = http_referer
        self.x_title = x_title
        self.reasoning_effort = (reasoning_effort or "").strip().lower()
        self._client = self._init_client()

    def _init_client(self) -> Any:
        if self.provider != "openrouter":
            raise ValueError(f"Unsupported provider: {self.provider}")

        from openai import OpenAI

        default_headers: dict[str, str] = {}
        if self.http_referer:
            default_headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            default_headers["X-Title"] = self.x_title

        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=default_headers or None,
        )

    @staticmethod
    def _as_int(value: Any) -> int:
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _as_cost(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace("$", "")
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)

        data: dict[str, Any] = {}
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
                if isinstance(dumped, dict):
                    data.update(dumped)
            except Exception:
                pass

        model_extra = getattr(value, "model_extra", None)
        if isinstance(model_extra, dict):
            data.update(model_extra)

        for attr in (
            "usage",
            "cost",
            "total_cost",
            "prompt_cost",
            "completion_cost",
            "input_cost",
            "output_cost",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            attr_value = getattr(value, attr, None)
            if attr_value is not None and attr not in data:
                data[attr] = attr_value

        return data

    def _extract_tokens(self, response: Any) -> int:
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0

        total_tokens = self._as_int(getattr(usage, "total_tokens", 0))
        if total_tokens > 0:
            return total_tokens

        usage_data = self._to_dict(usage)
        if "total_tokens" in usage_data:
            total_tokens = self._as_int(usage_data.get("total_tokens"))
            if total_tokens > 0:
                return total_tokens

        prompt_tokens = self._as_int(getattr(usage, "prompt_tokens", 0))
        completion_tokens = self._as_int(getattr(usage, "completion_tokens", 0))

        if prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens = self._as_int(usage_data.get("prompt_tokens", 0))
            completion_tokens = self._as_int(usage_data.get("completion_tokens", 0))

        return prompt_tokens + completion_tokens

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            message = response.choices[0].message
        except (AttributeError, IndexError, TypeError):
            return ""

        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(str(item.get("text", "")))
                else:
                    item_type = getattr(item, "type", "")
                    if item_type == "text":
                        text_parts.append(str(getattr(item, "text", "")))
            return "".join(text_parts)
        return str(content or "")

    def _extract_cost(self, response: Any) -> float:
        usage_data = self._to_dict(getattr(response, "usage", None))
        response_data = self._to_dict(response)

        cost_candidates = [
            usage_data.get("cost"),
            usage_data.get("total_cost"),
            response_data.get("cost"),
            response_data.get("total_cost"),
        ]

        for cost_candidate in cost_candidates:
            parsed = self._as_cost(cost_candidate)
            if parsed is not None:
                return parsed

        prompt_cost = self._as_cost(usage_data.get("prompt_cost"))
        completion_cost = self._as_cost(usage_data.get("completion_cost"))
        if prompt_cost is not None or completion_cost is not None:
            return (prompt_cost or 0.0) + (completion_cost or 0.0)

        input_cost = self._as_cost(usage_data.get("input_cost"))
        output_cost = self._as_cost(usage_data.get("output_cost"))
        if input_cost is not None or output_cost is not None:
            return (input_cost or 0.0) + (output_cost or 0.0)

        nested_usage = response_data.get("usage")
        if isinstance(nested_usage, dict):
            nested_cost = self._as_cost(nested_usage.get("cost") or nested_usage.get("total_cost"))
            if nested_cost is not None:
                return nested_cost

        return 0.0

    def _send_completion_request(
        self,
        system: str,
        user: str,
        max_tokens: int,
        reasoning_effort: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
            "temperature": self.temperature,
        }

        effort = (reasoning_effort or self.reasoning_effort or "").strip().lower()
        if effort:
            payload["extra_body"] = {
                "reasoning": {"effort": effort, "exclude": True},
            }

        return self._client.chat.completions.create(
            **payload,
        )

    @staticmethod
    def _parse_uci_candidate(board: chess.Board, candidate: str) -> chess.Move | None:
        normalized = candidate.lower().replace(" ", "")
        if not normalized:
            return None
        try:
            move = chess.Move.from_uci(normalized)
        except (ValueError, chess.InvalidMoveError):
            return None
        return move if move in board.legal_moves else None

    @staticmethod
    def _parse_san_candidate(board: chess.Board, candidate: str) -> chess.Move | None:
        raw = candidate.strip()
        if not raw:
            return None
        for san_candidate in (raw, raw[0:1].upper() + raw[1:]):
            normalized = san_candidate.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
            try:
                move = board.parse_san(normalized)
                if move in board.legal_moves:
                    return move
            except (ValueError, chess.InvalidMoveError, chess.AmbiguousMoveError):
                continue
        return None

    def _extract_move_from_response(self, board: chess.Board, response: str) -> chess.Move | None:
        cleaned = self._clean_response(response)
        for direct_candidate in (cleaned, response.strip()):
            move = self._parse_uci_candidate(board, direct_candidate)
            if move:
                return move
            move = self._parse_san_candidate(board, direct_candidate)
            if move:
                return move

        legal_uci = {move.uci() for move in board.legal_moves}
        for match in _UCI_CANDIDATE_RE.finditer(response):
            token = re.sub(r"\s+", "", match.group(1)).lower()
            if token in legal_uci:
                return chess.Move.from_uci(token)

        for san_token in _SAN_CANDIDATE_RE.findall(response):
            move = self._parse_san_candidate(board, san_token)
            if move:
                return move

        return None

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        legal_moves = [move.uci() for move in board.legal_moves]
        fen = board.fen()

        total_tokens = 0
        total_cost = 0.0
        illegal_attempts = 0
        start_time = time.monotonic()

        user_msg = (
            f"Position (FEN): {fen}\n"
            f"Legal moves: {', '.join(legal_moves)}\n"
            f"Your color: {'White' if board.turn == chess.WHITE else 'Black'}\n"
            f"Move number: {board.fullmove_number}\n"
            "Your move:"
        )

        for attempt in range(self.max_retries):
            try:
                api_result = self._call_api(SYSTEM_PROMPT, user_msg)
            except Exception:
                logger.warning(
                    "%s: API call failed (attempt %d/%d)",
                    self.name,
                    attempt + 1,
                    self.max_retries,
                    exc_info=True,
                )
                illegal_attempts += 1
                continue
            total_tokens += api_result.tokens
            total_cost += api_result.cost_usd

            raw_response = api_result.text
            move = self._extract_move_from_response(board, raw_response)
            if move:
                return MoveResult(
                    move=move,
                    tokens_used=total_tokens,
                    cost_usd=total_cost,
                    think_time_ms=int((time.monotonic() - start_time) * 1000),
                    illegal_attempts=illegal_attempts,
                    raw_response=raw_response,
                )

            illegal_attempts += 1
            cleaned = self._clean_response(raw_response)
            user_msg = (
                f"'{cleaned}' is NOT a valid move.\n"
                f"You MUST respond with exactly one move from this list: {', '.join(legal_moves)}\n"
                "Respond with ONLY the move, nothing else."
            )

        fallback = random.choice(list(board.legal_moves))
        return MoveResult(
            move=fallback,
            tokens_used=total_tokens,
            cost_usd=total_cost,
            think_time_ms=int((time.monotonic() - start_time) * 1000),
            illegal_attempts=illegal_attempts,
            raw_response=f"FALLBACK after {self.max_retries} retries",
        )

    def _clean_response(self, response: str) -> str:
        cleaned = response.strip()
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned)
        cleaned = cleaned.replace("```", "").strip()
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        if lines:
            cleaned = lines[0]
        return cleaned.strip('"\'` ')

    def _call_api(self, system: str, user: str) -> _ApiResult:
        if self.provider != "openrouter":
            raise ValueError(f"Unsupported provider: {self.provider}")

        response = self._send_completion_request(system, user, self.max_tokens)
        text = self._extract_text(response)
        tokens = self._extract_tokens(response)
        cost = self._extract_cost(response)

        finish_reason = ""
        try:
            finish_reason = str(getattr(response.choices[0], "finish_reason", "") or "")
        except (AttributeError, IndexError, TypeError):
            finish_reason = ""

        should_retry_for_length = not text.strip() and finish_reason == "length"
        recovery_effort = self.reasoning_effort
        recovery_tokens = max(self.max_tokens, MIN_REASONING_SAFE_MAX_TOKENS)
        can_retry = recovery_tokens != self.max_tokens or recovery_effort != self.reasoning_effort

        if should_retry_for_length and can_retry:
            expanded = self._send_completion_request(
                system,
                user,
                recovery_tokens,
                reasoning_effort=recovery_effort,
            )
            expanded_text = self._extract_text(expanded)
            tokens += self._extract_tokens(expanded)
            cost += self._extract_cost(expanded)
            if expanded_text:
                text = expanded_text

        return _ApiResult(text=text, tokens=tokens, cost_usd=cost)
