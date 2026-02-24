from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from src.config import settings

logger = logging.getLogger(__name__)

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)


def _migrate_schema(eng) -> None:
    """Add new columns to existing tables if they don't already exist."""
    migrations = [
        ("game", "status", "TEXT DEFAULT 'completed'"),
        ("game", "pairing_index", "INTEGER"),
        ("tournament", "player_names_json", "TEXT DEFAULT '[]'"),
        ("tournament", "completed_at", "TEXT"),
        ("tournament", "error_message", "TEXT"),
        ("player", "elo_confidence", "TEXT DEFAULT 'none'"),
        ("player", "elo_white_confidence", "TEXT DEFAULT 'none'"),
        ("player", "elo_black_confidence", "TEXT DEFAULT 'none'"),
        ("player", "elo_white_qualifying_moves", "INTEGER DEFAULT 0"),
        ("player", "elo_black_qualifying_moves", "INTEGER DEFAULT 0"),
        ("player", "benchmark_elo", "REAL DEFAULT 0.0"),
        ("player", "benchmark_games_played", "INTEGER DEFAULT 0"),
        ("player", "benchmark_wins", "INTEGER DEFAULT 0"),
        ("player", "benchmark_losses", "INTEGER DEFAULT 0"),
        ("player", "benchmark_draws", "INTEGER DEFAULT 0"),
        ("player", "benchmark_avg_cpl", "REAL DEFAULT 0.0"),
        ("player", "benchmark_avg_accuracy", "REAL DEFAULT 0.0"),
        ("player", "benchmark_total_tokens", "INTEGER DEFAULT 0"),
        ("player", "benchmark_total_cost_usd", "REAL DEFAULT 0.0"),
        ("player", "benchmark_total_blunders", "INTEGER DEFAULT 0"),
    ]
    with eng.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger.info("Migrated: added %s.%s", table, column)
            except Exception:
                conn.rollback()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_schema(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
