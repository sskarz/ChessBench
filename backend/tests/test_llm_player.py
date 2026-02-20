from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

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


class _FakeGoogleModels:
    def __init__(self, response: object) -> None:
        self._response = response

    def generate_content(self, *, model: str, contents: str, config: object) -> object:
        _ = (model, contents, config)
        return self._response


class _FakeGoogleClient:
    def __init__(self, response: object) -> None:
        self.models = _FakeGoogleModels(response)


class _GoogleStubPlayer(LLMPlayer):
    def __init__(self, response: object) -> None:
        self._response = response
        super().__init__(
            name="gemini-stub",
            provider="google",
            model="gemini-3.1-pro-preview",
            api_key="test-key",
            max_retries=2,
            temperature=0.0,
            max_tokens=16,
        )

    def _init_client(self):
        return _FakeGoogleClient(self._response)


def _install_fake_google_genai(monkeypatch) -> None:
    google_module = ModuleType("google")
    genai_module = ModuleType("google.genai")
    genai_module.types = SimpleNamespace(
        GenerateContentConfig=lambda **kwargs: kwargs,
        ThinkingConfig=lambda **kwargs: kwargs,
    )
    google_module.genai = genai_module
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)


def test_google_call_handles_none_usage_tokens(monkeypatch) -> None:
    _install_fake_google_genai(monkeypatch)
    response = SimpleNamespace(
        text="e2e4",
        usage_metadata=SimpleNamespace(prompt_token_count=None, candidates_token_count=None),
    )
    player = _GoogleStubPlayer(response)

    result = player._call_api("system", "user")

    assert result.text == "e2e4"
    assert result.tokens == 0


def test_google_call_handles_partial_none_usage_tokens(monkeypatch) -> None:
    _install_fake_google_genai(monkeypatch)
    response = SimpleNamespace(
        text="e2e4",
        usage_metadata=SimpleNamespace(prompt_token_count=7, candidates_token_count=None),
    )
    player = _GoogleStubPlayer(response)

    result = player._call_api("system", "user")

    assert result.tokens == 7


def test_google_get_move_works_when_usage_tokens_are_none(monkeypatch) -> None:
    _install_fake_google_genai(monkeypatch)
    response = SimpleNamespace(
        text="e2e4",
        usage_metadata=SimpleNamespace(prompt_token_count=None, candidates_token_count=None),
    )
    player = _GoogleStubPlayer(response)
    board = chess.Board()

    result = player.get_move(board, [])

    assert result.move == chess.Move.from_uci("e2e4")
    assert result.tokens_used == 0
    assert result.illegal_attempts == 0


def test_cost_estimation_handles_none_token_fields() -> None:
    player = StubLLMPlayer(responses=[])
    openai_usage = SimpleNamespace(prompt_tokens=None, completion_tokens=None)
    anthropic_usage = SimpleNamespace(input_tokens=None, output_tokens=None)

    assert player._estimate_cost(openai_usage) == 0.0
    assert player._estimate_cost_anthropic(anthropic_usage) == 0.0
