from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "ChessBench"

    # Deprecated key aliases kept for staged migration.
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    stockfish_path: str = "/usr/local/bin/stockfish"
    analysis_depth: int = 18
    stockfish_threads: int = 4
    stockfish_hash_mb: int = 256

    move_delay_seconds: float = 1.5
    max_moves_per_side: int = 150
    llm_max_retries: int = 5
    llm_temperature: float = 0.0
    llm_max_tokens: int = 128
    llm_reasoning_effort: str = ""

    database_url: str = "sqlite:///./arena.db"

    players: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {"name": "GPT-5.2", "provider": "openrouter", "model": "openai/gpt-5.2"},
            {
                "name": "Claude Opus",
                "provider": "openrouter",
                "model": "anthropic/claude-opus-4-6",
            },
            {"name": "Gemini 3 Flash", "provider": "openrouter", "model": "google/gemini-3-flash-preview"},
            {
                "name": "Stockfish-800",
                "provider": "engine",
                "model": "stockfish",
                "elo_limit": 800,
            },
        ]
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
