from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    database_url: str = "sqlite:///./arena.db"

    players: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {"name": "GPT-4o", "provider": "openai", "model": "gpt-4o"},
            {"name": "o4-mini", "provider": "openai", "model": "o4-mini"},
            {
                "name": "Claude Sonnet",
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
            },
            {"name": "Gemini 2.5 Pro", "provider": "google", "model": "gemini-2.5-pro"},
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
