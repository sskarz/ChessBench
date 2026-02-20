from __future__ import annotations

import logging
from typing import Any

from src.config import Settings
from src.players.base import PlayerAdapter
from src.players.engine_player import UCIEnginePlayer
from src.players.llm_player import LLMPlayer

logger = logging.getLogger(__name__)
_legacy_openrouter_key_warning_emitted = False


def _resolve_openrouter_api_key(settings: Settings) -> str:
    global _legacy_openrouter_key_warning_emitted

    key = str(settings.openrouter_api_key).strip()
    if key:
        return key

    fallback_sources = [
        ("OPENAI_API_KEY", settings.openai_api_key),
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        ("GOOGLE_API_KEY", settings.google_api_key),
    ]
    for env_var, value in fallback_sources:
        fallback = str(value).strip()
        if not fallback:
            continue
        if not _legacy_openrouter_key_warning_emitted:
            logger.warning(
                "OPENROUTER_API_KEY is not set. Using deprecated fallback %s; set OPENROUTER_API_KEY instead.",
                env_var,
            )
            _legacy_openrouter_key_warning_emitted = True
        return fallback

    return ""


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
            engine_path = str(raw.get("engine_path") or cfg.stockfish_path)
            try:
                player = UCIEnginePlayer(
                    name=name,
                    engine_path=engine_path,
                    time_limit=float(raw.get("time_limit", 0.2)),
                    skill_level=int(raw["skill_level"]) if "skill_level" in raw else None,
                    elo_limit=int(raw["elo_limit"]) if "elo_limit" in raw else None,
                )
            except Exception as exc:
                errors.append(
                    f"Failed to build engine player '{name}' "
                    f"(engine_path={engine_path}): {exc}"
                )
                continue
            players.append(player)
            continue

        if provider == "openrouter":
            api_key = str(raw.get("api_key") or _resolve_openrouter_api_key(cfg)).strip()
            if not api_key:
                errors.append(
                    "Skipping LLM player "
                    f"'{name}' ({provider}) because API key is missing "
                    "(set OPENROUTER_API_KEY or player.api_key)"
                )
                continue
            if not model:
                errors.append(f"Skipping LLM player '{name}' ({provider}) because model is missing")
                continue
            global_reasoning_effort = str(cfg.llm_reasoning_effort).strip()
            player_reasoning_effort = str(raw.get("reasoning_effort", "")).strip()
            if (
                global_reasoning_effort
                and player_reasoning_effort
                and player_reasoning_effort.lower() != global_reasoning_effort.lower()
            ):
                logger.warning(
                    "Ignoring player-specific reasoning_effort=%s for '%s'; "
                    "using global LLM_REASONING_EFFORT=%s for fair comparisons.",
                    player_reasoning_effort,
                    name,
                    global_reasoning_effort,
                )
            effective_reasoning_effort = global_reasoning_effort or player_reasoning_effort
            try:
                player = LLMPlayer(
                    name=name,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    max_retries=int(raw.get("max_retries", cfg.llm_max_retries)),
                    temperature=float(raw.get("temperature", cfg.llm_temperature)),
                    max_tokens=int(raw.get("max_tokens", cfg.llm_max_tokens)),
                    reasoning_effort=effective_reasoning_effort or None,
                    base_url=str(cfg.openrouter_base_url).strip() or "https://openrouter.ai/api/v1",
                    http_referer=str(cfg.openrouter_http_referer).strip(),
                    x_title=str(cfg.openrouter_x_title).strip(),
                )
            except Exception as exc:
                errors.append(f"Failed to build LLM player '{name}': {exc}")
                continue
            players.append(player)
            continue

        errors.append(
            f"Unsupported provider '{provider}' for player '{name}' "
            "(expected one of: engine, openrouter)"
        )

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
