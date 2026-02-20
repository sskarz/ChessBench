from __future__ import annotations

from types import SimpleNamespace

import chess
import pytest

from src.players.llm_player import LLMPlayer, _ApiResult


class StubLLMPlayer(LLMPlayer):
    def __init__(self, responses: list[_ApiResult], max_retries: int = 5) -> None:
        self._responses = responses
        super().__init__(
            name="stub",
            provider="openrouter",
            model="openai/gpt-4o",
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


class _FakeChatCompletions:
    def __init__(self, response: object) -> None:
        self._response = response

    def create(self, **kwargs) -> object:
        _ = kwargs
        return self._response


class _QueuedFakeChatCompletions:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs) -> object:
        self.calls.append(kwargs)
        if self._responses:
            return self._responses.pop(0)
        raise RuntimeError("No queued response available")


class _FakeChat:
    def __init__(self, response: object) -> None:
        self.completions = _FakeChatCompletions(response)


class _QueuedFakeChat:
    def __init__(self, responses: list[object]) -> None:
        self.completions = _QueuedFakeChatCompletions(responses)


class _FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.chat = _FakeChat(response)


class _QueuedFakeOpenAIClient:
    def __init__(self, responses: list[object]) -> None:
        self.chat = _QueuedFakeChat(responses)


class _OpenRouterStubPlayer(LLMPlayer):
    def __init__(self, response: object) -> None:
        self._response = response
        super().__init__(
            name="openrouter-stub",
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-key",
            max_retries=2,
            temperature=0.0,
            max_tokens=16,
        )

    def _init_client(self):
        return _FakeOpenAIClient(self._response)


class _QueuedOpenRouterStubPlayer(LLMPlayer):
    def __init__(
        self,
        responses: list[object],
        max_tokens: int = 16,
        reasoning_effort: str | None = None,
    ) -> None:
        self._responses = responses
        super().__init__(
            name="openrouter-stub",
            provider="openrouter",
            model="openai/gpt-5.2",
            api_key="test-key",
            max_retries=2,
            temperature=0.0,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )

    def _init_client(self):
        return _QueuedFakeOpenAIClient(self._responses)


def _make_response(*, text: str = "e2e4", usage: object | None = None, model_extra: dict | None = None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=usage,
        model_extra=model_extra or {},
    )


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


def test_llm_player_extracts_uci_from_verbose_response() -> None:
    board = chess.Board()
    player = StubLLMPlayer(
        responses=[_ApiResult(text="Best move is e2e4 because it controls the center.", tokens=3, cost_usd=0.0)],
        max_retries=2,
    )

    result = player.get_move(board, [])

    assert result.move == chess.Move.from_uci("e2e4")
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


def test_llm_player_parses_moves_across_five_ply_game() -> None:
    board = chess.Board()
    history: list[chess.Move] = []
    player = StubLLMPlayer(
        responses=[
            _ApiResult(text="e2e4", tokens=1, cost_usd=0.0),
            _ApiResult(text="Best is e7e5 to mirror center control.", tokens=1, cost_usd=0.0),
            _ApiResult(text="Nf3", tokens=1, cost_usd=0.0),
            _ApiResult(text="I'll play Nc6.", tokens=1, cost_usd=0.0),
            _ApiResult(text="```Bb5```", tokens=1, cost_usd=0.0),
        ],
        max_retries=1,
    )

    expected_sans = ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    parsed_sans: list[str] = []

    for expected_san in expected_sans:
        result = player.get_move(board, history)
        assert result.move in board.legal_moves
        assert result.illegal_attempts == 0

        san = board.san(result.move)
        parsed_sans.append(san)
        board.push(result.move)
        history.append(result.move)

        assert san == expected_san

    assert len(history) == 5
    assert parsed_sans == expected_sans


def test_call_api_handles_none_usage_tokens_and_missing_cost() -> None:
    response = _make_response(
        usage=SimpleNamespace(total_tokens=None, prompt_tokens=None, completion_tokens=None, model_extra={}),
    )
    player = _OpenRouterStubPlayer(response)

    result = player._call_api("system", "user")

    assert result.text == "e2e4"
    assert result.tokens == 0
    assert result.cost_usd == 0.0


def test_call_api_handles_partial_none_usage_tokens() -> None:
    response = _make_response(
        usage=SimpleNamespace(total_tokens=None, prompt_tokens=7, completion_tokens=None, model_extra={}),
    )
    player = _OpenRouterStubPlayer(response)

    result = player._call_api("system", "user")

    assert result.tokens == 7


def test_call_api_reads_cost_from_usage_fields() -> None:
    response = _make_response(
        usage=SimpleNamespace(
            total_tokens=10,
            prompt_tokens=4,
            completion_tokens=6,
            model_extra={"cost": "0.00123"},
        ),
    )
    player = _OpenRouterStubPlayer(response)

    result = player._call_api("system", "user")

    assert result.tokens == 10
    assert result.cost_usd == pytest.approx(0.00123)


def test_call_api_reads_cost_from_response_model_extra() -> None:
    response = _make_response(
        usage=SimpleNamespace(total_tokens=10, prompt_tokens=4, completion_tokens=6, model_extra={}),
        model_extra={"total_cost": "0.0025"},
    )
    player = _OpenRouterStubPlayer(response)

    result = player._call_api("system", "user")

    assert result.cost_usd == pytest.approx(0.0025)


def test_unsupported_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        LLMPlayer(name="bad", provider="openai", model="gpt-4o", api_key="k")


def test_call_api_retries_with_larger_budget_when_reasoning_exhausts_tokens() -> None:
    first = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="length")],
        usage=SimpleNamespace(
            total_tokens=110,
            prompt_tokens=94,
            completion_tokens=16,
            model_extra={"cost": "0.0003885"},
        ),
        model_extra={},
    )
    second = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="e2e4"), finish_reason="stop")],
        usage=SimpleNamespace(
            total_tokens=126,
            prompt_tokens=94,
            completion_tokens=32,
            model_extra={"cost": "0.0006125"},
        ),
        model_extra={},
    )
    player = _QueuedOpenRouterStubPlayer([first, second], max_tokens=16, reasoning_effort="low")

    result = player._call_api("system", "user")

    assert result.text == "e2e4"
    assert result.tokens == 236
    assert result.cost_usd == pytest.approx(0.001001)
    assert len(player._client.chat.completions.calls) == 2
    assert player._client.chat.completions.calls[0]["max_completion_tokens"] == 16
    assert player._client.chat.completions.calls[1]["max_completion_tokens"] == 1024
    assert player._client.chat.completions.calls[0]["extra_body"]["reasoning"]["effort"] == "low"
    assert player._client.chat.completions.calls[1]["extra_body"]["reasoning"]["effort"] == "low"
