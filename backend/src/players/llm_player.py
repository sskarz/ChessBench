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
- Think carefully about tactics, strategy, and positional advantage"""


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
        max_tokens: int = 16,
    ) -> None:
        self.name = name
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = self._init_client()

    def _init_client(self) -> Any:
        if self.provider == "openai":
            from openai import OpenAI

            return OpenAI(api_key=self.api_key)

        if self.provider == "anthropic":
            import anthropic

            return anthropic.Anthropic(api_key=self.api_key)

        if self.provider == "google":
            from google import genai

            return genai.Client(api_key=self.api_key)

        raise ValueError(f"Unsupported provider: {self.provider}")

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

        for _attempt in range(self.max_retries):
            try:
                api_result = self._call_api(SYSTEM_PROMPT, user_msg)
            except Exception:
                logger.warning(
                    "%s: API call failed (attempt %d/%d)",
                    self.name,
                    _attempt + 1,
                    self.max_retries,
                    exc_info=True,
                )
                illegal_attempts += 1
                continue
            total_tokens += api_result.tokens
            total_cost += api_result.cost_usd

            raw_response = api_result.text
            cleaned = self._clean_response(raw_response)
            uci_candidate = cleaned.lower().replace(" ", "")

            try:
                move = chess.Move.from_uci(uci_candidate)
                if move in board.legal_moves:
                    return MoveResult(
                        move=move,
                        tokens_used=total_tokens,
                        cost_usd=total_cost,
                        think_time_ms=int((time.monotonic() - start_time) * 1000),
                        illegal_attempts=illegal_attempts,
                        raw_response=raw_response,
                    )
            except (ValueError, chess.InvalidMoveError):
                pass

            try:
                move = board.parse_san(cleaned)
                if move in board.legal_moves:
                    return MoveResult(
                        move=move,
                        tokens_used=total_tokens,
                        cost_usd=total_cost,
                        think_time_ms=int((time.monotonic() - start_time) * 1000),
                        illegal_attempts=illegal_attempts,
                        raw_response=raw_response,
                    )
            except (ValueError, chess.InvalidMoveError, chess.AmbiguousMoveError):
                pass

            illegal_attempts += 1
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
        if self.provider == "openai":
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_completion_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            text = response.choices[0].message.content or ""
            usage = response.usage
            tokens = usage.total_tokens if usage else 0
            cost = self._estimate_cost(usage) if usage else 0.0
            return _ApiResult(text=text, tokens=tokens, cost_usd=cost)

        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=self.temperature,
            )
            text = response.content[0].text if response.content else ""
            usage = response.usage
            tokens = (usage.input_tokens + usage.output_tokens) if usage else 0
            cost = self._estimate_cost_anthropic(usage) if usage else 0.0
            return _ApiResult(text=text, tokens=tokens, cost_usd=cost)

        if self.provider == "google":
            from google.genai import types

            response = self._client.models.generate_content(
                model=self.model,
                contents=f"{system}\n\n{user}",
                config=types.GenerateContentConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                ),
            )
            text = getattr(response, "text", "") or ""
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
            candidates_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
            tokens = prompt_tokens + candidates_tokens
            return _ApiResult(text=text, tokens=tokens, cost_usd=0.0)

        raise ValueError(f"Unsupported provider: {self.provider}")

    def _estimate_cost(self, usage: Any) -> float:
        pricing = {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-5.2": (2.00, 8.00),
            "o4-mini": (1.10, 4.40),
            "gpt-3.5-turbo-instruct": (1.50, 2.00),
        }
        input_rate, output_rate = pricing.get(self.model, (2.50, 10.00))
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        input_cost = (prompt_tokens / 1_000_000) * input_rate
        output_cost = (completion_tokens / 1_000_000) * output_rate
        return input_cost + output_cost

    def _estimate_cost_anthropic(self, usage: Any) -> float:
        pricing = {
            "claude-sonnet-4-5-20250929": (3.00, 15.00),
            "claude-haiku-4-5-20251001": (0.80, 4.00),
            "claude-opus-4-6": (15.00, 75.00),
        }
        input_rate, output_rate = pricing.get(self.model, (3.00, 15.00))
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
