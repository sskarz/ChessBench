from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    provider: str
    model_id: str
    elo: float = Field(default=1200.0)
    games_played: int = Field(default=0)
    wins: int = Field(default=0)
    losses: int = Field(default=0)
    draws: int = Field(default=0)
    avg_cpl: float = Field(default=0.0)
    avg_accuracy: float = Field(default=0.0)
    total_tokens: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tournament_id: int | None = Field(default=None, foreign_key="tournament.id")
    white_id: int = Field(foreign_key="player.id")
    black_id: int = Field(foreign_key="player.id")
    result: str
    termination: str
    pgn: str
    moves_count: int
    white_avg_cpl: float
    black_avg_cpl: float
    white_accuracy: float
    black_accuracy: float
    white_blunders: int
    black_blunders: int
    white_mistakes: int
    black_mistakes: int
    white_illegal_attempts: int
    black_illegal_attempts: int
    white_tokens: int
    black_tokens: int
    white_cost_usd: float
    black_cost_usd: float
    duration_seconds: float
    opening_name: str | None = None
    opening_eco: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class MoveAnalysis(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    move_number: int
    color: str
    move_uci: str
    move_san: str
    fen_before: str
    fen_after: str
    eval_before_cp: int | None = None
    eval_after_cp: int | None = None
    best_move_uci: str | None = None
    best_move_san: str | None = None
    centipawn_loss: int
    classification: str
    is_book_move: bool = False
    think_time_ms: int | None = None
    tokens_used: int | None = None
    illegal_attempts: int = 0


class Tournament(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    format: str
    rounds: int
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=datetime.utcnow)
