from __future__ import annotations

from typing import Any

from src.config import Settings
from src.players.base import PlayerAdapter
from src.players.engine_player import UCIEnginePlayer
from src.players.llm_player import LLMPlayer


def _api_key_for_provider(provider: str, settings: Settings) -> str:
    mapping = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "google": settings.google_api_key,
    }
    return mapping.get(provider, "")


def build_players_from_settings(cfg: Settings) -> tuple[list[PlayerAdapter], list[str]]:
    players: list[PlayerAdapter] = []
    errors: list[str] = []

    for raw in cfg.players:
        provider = str(raw.get("provider", "")).strip().lower()
        name = str(raw.get("name", "")).strip()
        model = str(raw.get("model", "")).strip()

        if not provider or not name:
            errors.append(f"Skipping player config without provider/name: {raw}")
            continue

        if provider == "engine":
            try:
                player = UCIEnginePlayer(
                    name=name,
                    engine_path=str(raw.get("engine_path") or cfg.stockfish_path),
                    time_limit=float(raw.get("time_limit", 0.2)),
                    skill_level=int(raw["skill_level"]) if "skill_level" in raw else None,
                    elo_limit=int(raw["elo_limit"]) if "elo_limit" in raw else None,
                )
            except Exception as exc:
                errors.append(f"Failed to build engine player '{name}': {exc}")
                continue
            players.append(player)
            continue

        if provider in {"openai", "anthropic", "google"}:
            api_key = str(raw.get("api_key") or _api_key_for_provider(provider, cfg)).strip()
            if not api_key:
                errors.append(f"Skipping LLM player '{name}' ({provider}) because API key is missing")
                continue
            if not model:
                errors.append(f"Skipping LLM player '{name}' ({provider}) because model is missing")
                continue
            try:
                player = LLMPlayer(
                    name=name,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    max_retries=int(raw.get("max_retries", cfg.llm_max_retries)),
                    temperature=float(raw.get("temperature", cfg.llm_temperature)),
                    max_tokens=int(raw.get("max_tokens", 16)),
                )
            except Exception as exc:
                errors.append(f"Failed to build LLM player '{name}': {exc}")
                continue
            players.append(player)
            continue

        errors.append(f"Unsupported provider '{provider}' for player '{name}'")

    return players, errors


def describe_player_config(player: PlayerAdapter) -> dict[str, Any]:
    provider = "engine"
    model = "stockfish"

    if isinstance(player, LLMPlayer):
        provider = player.provider
        model = player.model
    elif isinstance(player, UCIEnginePlayer):
        provider = "engine"
        model = "stockfish"

    return {
        "name": player.get_name(),
        "provider": provider,
        "model": model,
    }
