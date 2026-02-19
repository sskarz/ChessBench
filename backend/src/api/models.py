from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StandingsEntry(BaseModel):
    name: str
    elo: float
    wins: int
    losses: int
    draws: int
    avg_accuracy: float
    avg_cpl: float
    blunder_rate: float
    total_cost_usd: float


class GameSummary(BaseModel):
    id: int
    white: str
    black: str
    result: str
    termination: str
    moves_count: int
    white_accuracy: float
    black_accuracy: float
    duration_seconds: float
    completed_at: datetime | None = None


class GameListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[GameSummary]


class GameDetail(GameSummary):
    pgn: str
    white_avg_cpl: float
    black_avg_cpl: float
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
    started_at: datetime


class MoveAnalysisEntry(BaseModel):
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
    think_time_ms: int | None = None
    tokens_used: int | None = None
    illegal_attempts: int


class GameAnalysisResponse(BaseModel):
    game_id: int
    moves: list[MoveAnalysisEntry]


class PlayerStats(BaseModel):
    name: str
    provider: str
    model_id: str
    elo: float
    games_played: int
    wins: int
    losses: int
    draws: int
    avg_cpl: float
    avg_accuracy: float
    total_tokens: int
    total_cost_usd: float
    blunder_rate: float


class LiveStateResponse(BaseModel):
    status: Literal["idle", "running", "completed", "error"]
    run_id: str | None = None
    current_game: dict | None = None
    last_event: dict | None = None
    latest_standings: list[StandingsEntry] = Field(default_factory=list)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    error: str | None = None


class TournamentStartRequest(BaseModel):
    rounds: int = Field(default=1, ge=1)


class TournamentStartResponse(BaseModel):
    status: str
    run_id: str
    rounds: int
    players: list[dict]


class HealthResponse(BaseModel):
    status: str
    db_ok: bool
    live_status: str
