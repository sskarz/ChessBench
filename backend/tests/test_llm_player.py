from __future__ import annotations

import chess

from src.players.llm_player import LLMPlayer, _ApiResult


class StubLLMPlayer(LLMPlayer):
    def __init__(self, responses: list[_ApiResult], max_retries: int = 5) -> None:
        self._responses = responses
        super().__init__(
            name="stub",
            provider="openai",
            model="gpt-4o",
            api_key="test-key",
            max_retries=max_retries,
            temperature=0.0,
            max_tokens=16,
        )

    def _init_client(self):
        return object()

    def _call_api(self, system: str, user: str) -> _ApiResult:
        _ = (system, user)
        if self._responses:
            return self._responses.pop(0)
        return _ApiResult(text="e2e4", tokens=1, cost_usd=0.0)


def test_llm_player_retries_then_accepts_uci() -> None:
    board = chess.Board()
    player = StubLLMPlayer(
        responses=[
            _ApiResult(text="not-a-move", tokens=11, cost_usd=0.0011),
            _ApiResult(text="e2e4", tokens=9, cost_usd=0.0009),
        ],
        max_retries=3,
    )

    result = player.get_move(board, [])

    assert result.move == chess.Move.from_uci("e2e4")
    assert result.illegal_attempts == 1
    assert result.tokens_used == 20
    assert round(result.cost_usd, 4) == 0.002


def test_llm_player_accepts_san_output() -> None:
    board = chess.Board()
    player = StubLLMPlayer(responses=[_ApiResult(text="Nf3", tokens=3, cost_usd=0.0)])

    result = player.get_move(board, [])

    assert result.move == board.parse_san("Nf3")
    assert result.illegal_attempts == 0


def test_llm_player_fallback_after_retry_exhaustion() -> None:
    board = chess.Board()
    player = StubLLMPlayer(
        responses=[
            _ApiResult(text="???", tokens=1, cost_usd=0.0),
            _ApiResult(text="still bad", tokens=1, cost_usd=0.0),
        ],
        max_retries=2,
    )

    result = player.get_move(board, [])

    assert result.move in board.legal_moves
    assert result.illegal_attempts == 2
