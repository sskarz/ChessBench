from __future__ import annotations

import logging

from src.config import Settings
from src.game import player_factory
from src.game.player_factory import build_players_from_settings, describe_player_config
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
