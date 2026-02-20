from __future__ import annotations

import logging

from src import config as config_module
from src.config import Settings
from src.game import player_factory
from src.game.player_factory import build_players_from_settings, describe_player_config
from src.players.engine_player import UCIEnginePlayer
from src.players.llm_player import LLMPlayer


def _patch_llm_init_client(monkeypatch) -> None:
    monkeypatch.setattr(LLMPlayer, "_init_client", lambda self: object())


def test_build_players_accepts_openrouter_provider(monkeypatch) -> None:
    _patch_llm_init_client(monkeypatch)
    cfg = Settings(
        openrouter_api_key="or-key",
        players=[
            {
                "name": "Bench GPT",
                "provider": "openrouter",
                "model": "openai/gpt-4o",
            }
        ],
    )

    players, errors = build_players_from_settings(cfg)

    assert errors == []
    assert len(players) == 1
    assert players[0].get_name() == "Bench GPT"
    assert describe_player_config(players[0]) == {
        "name": "Bench GPT",
        "provider": "openrouter",
        "model": "openai/gpt-4o",
    }


def test_build_players_rejects_legacy_provider(monkeypatch) -> None:
    _patch_llm_init_client(monkeypatch)
    cfg = Settings(
        openrouter_api_key="or-key",
        players=[
            {
                "name": "Legacy GPT",
                "provider": "openai",
                "model": "gpt-4o",
            }
        ],
    )

    players, errors = build_players_from_settings(cfg)

    assert players == []
    assert len(errors) == 1
    assert "Unsupported provider 'openai'" in errors[0]


def test_build_players_uses_deprecated_key_fallback(monkeypatch, caplog) -> None:
    _patch_llm_init_client(monkeypatch)
    monkeypatch.setattr(player_factory, "_legacy_openrouter_key_warning_emitted", False)

    cfg = Settings(
        openrouter_api_key="",
        openai_api_key="legacy-key",
        players=[
            {
                "name": "Fallback",
                "provider": "openrouter",
                "model": "openai/gpt-4o",
            }
        ],
    )

    with caplog.at_level(logging.WARNING):
        players, errors = build_players_from_settings(cfg)

    assert errors == []
    assert len(players) == 1
    assert "Using deprecated fallback OPENAI_API_KEY" in caplog.text


def test_build_players_requires_api_key(monkeypatch) -> None:
    _patch_llm_init_client(monkeypatch)
    cfg = Settings(
        openrouter_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        google_api_key="",
        players=[
            {
                "name": "No Key",
                "provider": "openrouter",
                "model": "openai/gpt-4o",
            }
        ],
    )

    players, errors = build_players_from_settings(cfg)

    assert players == []
    assert len(errors) == 1
    assert "API key is missing" in errors[0]


def test_settings_auto_detects_stockfish_path(monkeypatch) -> None:
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    monkeypatch.setattr(config_module.shutil, "which", lambda _cmd: "/tmp/stockfish")

    cfg = Settings(_env_file=None)

    assert cfg.stockfish_path == "/tmp/stockfish"


def test_build_players_engine_error_includes_engine_path(monkeypatch) -> None:
    def _boom(self, *args, **kwargs) -> None:
        _ = (self, args, kwargs)
        raise FileNotFoundError("stockfish not found")

    monkeypatch.setattr(UCIEnginePlayer, "__init__", _boom)
    cfg = Settings(
        stockfish_path="/tmp/missing-stockfish",
        players=[
            {
                "name": "SF",
                "provider": "engine",
                "model": "stockfish",
            }
        ],
    )

    players, errors = build_players_from_settings(cfg)

    assert players == []
    assert len(errors) == 1
    assert "engine_path=/tmp/missing-stockfish" in errors[0]


def test_build_players_prefers_global_reasoning_effort_for_fairness(monkeypatch, caplog) -> None:
    _patch_llm_init_client(monkeypatch)
    cfg = Settings(
        openrouter_api_key="or-key",
        llm_reasoning_effort="low",
        players=[
            {
                "name": "Uniform",
                "provider": "openrouter",
                "model": "openai/gpt-4o",
                "reasoning_effort": "high",
            }
        ],
    )

    with caplog.at_level(logging.WARNING):
        players, errors = build_players_from_settings(cfg)

    assert errors == []
    assert len(players) == 1
    assert isinstance(players[0], LLMPlayer)
    assert players[0].reasoning_effort == "low"
    assert "Ignoring player-specific reasoning_effort=high" in caplog.text


def test_build_players_uses_player_reasoning_effort_when_global_blank(monkeypatch) -> None:
    _patch_llm_init_client(monkeypatch)
    cfg = Settings(
        openrouter_api_key="or-key",
        llm_reasoning_effort="",
        players=[
            {
                "name": "PlayerScoped",
                "provider": "openrouter",
                "model": "openai/gpt-4o",
                "reasoning_effort": "medium",
            }
        ],
    )

    players, errors = build_players_from_settings(cfg)

    assert errors == []
    assert len(players) == 1
    assert isinstance(players[0], LLMPlayer)
    assert players[0].reasoning_effort == "medium"
