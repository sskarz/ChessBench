from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from src.analysis.elo_estimator import estimate_elo_from_aggregate
from src.config import Settings
from src.db.models import Game, MoveAnalysis, Player, Tournament
from src.game.orchestrator import LiveMoveEvent
from src.game.scheduler import ParallelScheduler
from src.players.base import PlayerAdapter

logger = logging.getLogger(__name__)

BenchmarkEventCallback = Callable[[dict[str, Any]], Awaitable[None]]
SessionFactory = Callable[[], Session]


def _generate_schedule(
    num_players: int, sf_index: int, rounds: int = 1
) -> list[tuple[int, int, int, int]]:
    """Generate benchmark pairings: each LLM plays 2 games vs Stockfish per round."""
    schedule: list[tuple[int, int, int, int]] = []
    idx = 0
    for r in range(1, rounds + 1):
        for i in range(num_players):
            if i == sf_index:
                continue
            schedule.append((r, idx, i, sf_index))
            idx += 1
            schedule.append((r, idx, sf_index, i))
            idx += 1
    return schedule


def _is_benchmark_anchor_row(player: Player) -> bool:
    return (
        player.provider == "engine"
        and player.model_id == "stockfish"
        and player.name.startswith("Stockfish-")
    )


class BenchmarkManager:
    def __init__(
        self,
        players: list[PlayerAdapter],
        session_factory: SessionFactory,
        event_callback: BenchmarkEventCallback | None = None,
        rounds: int = 1,
        player_descriptors: dict[str, dict[str, str]] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.players = players
        self.session_factory = session_factory
        self.event_callback = event_callback
        self.rounds = rounds
        self.player_descriptors = player_descriptors or {}
        self.settings = settings or Settings()
        self._run_lock = asyncio.Lock()

    async def run_benchmark(self, rounds: int = 1) -> dict[str, Any]:
        """Run benchmark mode: each LLM plays 2 games vs Stockfish per round."""
        if self._run_lock.locked():
            raise RuntimeError("Benchmark is already running")

        async with self._run_lock:
            # Find the Stockfish player index
            sf_index: int | None = None
            for i, p in enumerate(self.players):
                desc = self.player_descriptors.get(p.get_name(), {})
                if desc.get("provider") == "engine":
                    sf_index = i
                    break
            if sf_index is None:
                raise ValueError("No engine player found for benchmark")

            with self.session_factory() as session:
                player_ids = self._ensure_players(session)
                next_game_id = self._next_game_id(session)
                session.commit()

            player_names = [p.get_name() for p in self.players]
            schedule = _generate_schedule(len(self.players), sf_index, rounds)

            with self.session_factory() as session:
                tournament = Tournament(
                    name=f"Benchmark {datetime.utcnow().isoformat()}",
                    format="benchmark",
                    rounds=rounds,
                    status="running",
                    player_names_json=json.dumps(player_names),
                )
                session.add(tournament)
                session.commit()
                session.refresh(tournament)
                tournament_id = tournament.id

            pre_allocated_game_ids: dict[int, int] = {}
            for _, pairing_idx, _, _ in schedule:
                pre_allocated_game_ids[pairing_idx] = next_game_id
                next_game_id += 1

            with self.session_factory() as session:
                for _, pairing_idx, w_idx, b_idx in schedule:
                    game_id = pre_allocated_game_ids[pairing_idx]
                    white = self.players[w_idx]
                    black = self.players[b_idx]
                    db_game = Game(
                        id=game_id,
                        tournament_id=tournament_id,
                        white_id=player_ids[white.get_name()],
                        black_id=player_ids[black.get_name()],
                        status="in_progress",
                        pairing_index=pairing_idx,
                    )
                    session.add(db_game)
                session.commit()

            try:
                scheduler = ParallelScheduler(
                    players=self.players,
                    player_ids=player_ids,
                    tournament_id=tournament_id,
                    session_factory=self.session_factory,
                    event_callback=self.event_callback,
                    settings=self.settings,
                    player_descriptors=self.player_descriptors,
                    persist_move=self._persist_move,
                    on_move_event=self._on_move_event,
                    finalize_game=self._finalize_game,
                    get_standings=self.get_standings,
                    abandon_game=self._abandon_game,
                )
                scheduler._max_concurrent = 2
                games_played = await scheduler.run_schedule(
                    schedule=schedule,
                    pre_allocated_game_ids=pre_allocated_game_ids,
                    allow_concurrent_players=True,
                )

                with self.session_factory() as session:
                    t = session.get(Tournament, tournament_id)
                    if t:
                        t.status = "completed"
                        t.completed_at = datetime.utcnow()
                    session.commit()
                    final_standings = self.get_standings(session=session)

            except Exception:
                with self.session_factory() as session:
                    t = session.get(Tournament, tournament_id)
                    if t:
                        t.status = "error"
                        t.error_message = "Benchmark interrupted"
                    session.commit()
                raise

            return {
                "games_played": games_played,
                "standings": final_standings,
            }

    def _finalize_game(
        self,
        session: Session,
        game_id: int,
        game_result: dict[str, Any],
        white_player_id: int,
        black_player_id: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        """Finalize a benchmark game: persist stats and estimate Elo from CPL."""
        white_row = session.get(Player, white_player_id)
        black_row = session.get(Player, black_player_id)
        if white_row is None or black_row is None:
            raise RuntimeError("Missing player row while saving benchmark game")

        game = session.get(Game, game_id)
        if game is None:
            raise RuntimeError(f"Game {game_id} not found for finalization")

        game.status = "completed"
        game.result = game_result["result"]
        game.termination = game_result["termination"]
        game.pgn = game_result["pgn"]
        game.moves_count = game_result["moves_count"]
        game.white_avg_cpl = game_result["white_avg_cpl"]
        game.black_avg_cpl = game_result["black_avg_cpl"]
        game.white_accuracy = game_result["white_accuracy"]
        game.black_accuracy = game_result["black_accuracy"]
        game.white_blunders = game_result["white_blunders"]
        game.black_blunders = game_result["black_blunders"]
        game.white_mistakes = game_result["white_mistakes"]
        game.black_mistakes = game_result["black_mistakes"]
        game.white_illegal_attempts = game_result["white_illegal_attempts"]
        game.black_illegal_attempts = game_result["black_illegal_attempts"]
        game.white_tokens = game_result["white_tokens"]
        game.black_tokens = game_result["black_tokens"]
        game.white_cost_usd = game_result["white_cost_usd"]
        game.black_cost_usd = game_result["black_cost_usd"]
        game.duration_seconds = game_result["duration_seconds"]
        game.opening_name = game_result.get("opening_name")
        game.opening_eco = game_result.get("opening_eco")
        game.started_at = started_at
        game.completed_at = completed_at

        white_is_engine = white_row.provider == "engine"
        black_is_engine = black_row.provider == "engine"

        result = game_result["result"]

        if not white_is_engine:
            self._apply_player_result(
                player=white_row,
                result=result,
                as_white=True,
                avg_cpl=game_result["white_avg_cpl"],
                accuracy=game_result["white_accuracy"],
                tokens=game_result["white_tokens"],
                cost=game_result["white_cost_usd"],
                blunders=game_result["white_blunders"],
            )
        if not black_is_engine:
            self._apply_player_result(
                player=black_row,
                result=result,
                as_white=False,
                avg_cpl=game_result["black_avg_cpl"],
                accuracy=game_result["black_accuracy"],
                tokens=game_result["black_tokens"],
                cost=game_result["black_cost_usd"],
                blunders=game_result["black_blunders"],
            )

        benchmark_elo = self.settings.benchmark_stockfish_elo
        eval_cap = self.settings.benchmark_eval_cap
        min_qualifying_moves = self.settings.benchmark_min_qualifying_moves

        llm_rows = [r for r in (white_row, black_row) if r.provider != "engine"]
        for row in llm_rows:
            player_id = row.id
            self._recompute_elo(
                session, row, player_id,
                eval_cap, min_qualifying_moves, benchmark_elo,
            )

    def _recompute_elo(
        self,
        session: Session,
        row: Player,
        player_id: int,
        eval_cap: int,
        min_qualifying_moves: int,
        benchmark_elo: float,
    ) -> None:
        """Recompute a player's Elo from all qualifying moves."""
        for color, elo_attr, qm_attr, conf_attr, is_white in [
            ("white", "elo_white", "elo_white_qualifying_moves", "elo_white_confidence", True),
            ("black", "elo_black", "elo_black_qualifying_moves", "elo_black_confidence", False),
        ]:
            player_col = Game.white_id if is_white else Game.black_id
            all_moves = session.exec(
                select(MoveAnalysis)
                .join(Game, MoveAnalysis.game_id == Game.id)
                .join(Tournament, Game.tournament_id == Tournament.id)
                .where(
                    Tournament.format == "benchmark",
                    player_col == player_id,
                    Game.status == "completed",
                    MoveAnalysis.color == color,
                    MoveAnalysis.is_book_move == False,  # noqa: E712
                    MoveAnalysis.eval_before_cp.is_not(None),  # type: ignore[union-attr]
                    func.abs(MoveAnalysis.eval_before_cp) <= eval_cap,
                )
            ).all()

            qm = len(all_moves)
            setattr(row, qm_attr, qm)

            if qm == 0:
                setattr(row, elo_attr, 0.0)
                setattr(row, conf_attr, "none")
                continue

            setattr(row, conf_attr, "high" if qm >= min_qualifying_moves else "low")

            avg_cpl = sum(m.centipawn_loss for m in all_moves) / qm

            games_as_side = session.exec(
                select(Game)
                .join(Tournament, Game.tournament_id == Tournament.id)
                .where(
                    Tournament.format == "benchmark",
                    player_col == player_id,
                    Game.status == "completed",
                )
            ).all()
            if is_white:
                wins = sum(1 for g in games_as_side if g.result == "1-0")
                losses = sum(1 for g in games_as_side if g.result == "0-1")
            else:
                wins = sum(1 for g in games_as_side if g.result == "0-1")
                losses = sum(1 for g in games_as_side if g.result == "1-0")
            draws = sum(1 for g in games_as_side if g.result == "1/2-1/2")

            estimated = estimate_elo_from_aggregate(avg_cpl, wins, draws, losses, benchmark_elo)
            setattr(row, elo_attr, estimated)

        qm_w = row.elo_white_qualifying_moves
        qm_b = row.elo_black_qualifying_moves
        total = qm_w + qm_b
        if total > 0:
            elo_w = row.elo_white if qm_w > 0 else 0.0
            elo_b = row.elo_black if qm_b > 0 else 0.0
            row.elo = round((elo_w * qm_w + elo_b * qm_b) / total, 1)
            row.elo_confidence = (
                "high" if qm_w >= min_qualifying_moves and qm_b >= min_qualifying_moves
                else "low"
            )
        else:
            row.elo = 0.0
            row.elo_confidence = "none"

    async def _persist_move(self, game_id: int, analysis_record: dict[str, Any]) -> None:
        """Write a single MoveAnalysis row immediately after a move is analyzed."""
        with self.session_factory() as session:
            session.add(
                MoveAnalysis(
                    game_id=game_id,
                    move_number=analysis_record["move_number"],
                    color=analysis_record["color"],
                    move_uci=analysis_record["move_uci"],
                    move_san=analysis_record["move_san"],
                    fen_before=analysis_record["fen_before"],
                    fen_after=analysis_record["fen_after"],
                    eval_before_cp=analysis_record["eval_before_cp"],
                    eval_after_cp=analysis_record["eval_after_cp"],
                    best_move_uci=analysis_record["best_move_uci"],
                    best_move_san=analysis_record["best_move_san"],
                    centipawn_loss=analysis_record["centipawn_loss"],
                    classification=analysis_record["classification"],
                    think_time_ms=analysis_record["think_time_ms"],
                    tokens_used=analysis_record["tokens_used"],
                    illegal_attempts=analysis_record["illegal_attempts"],
                )
            )
            session.commit()

    async def _on_move_event(self, event: LiveMoveEvent) -> None:
        await self._emit(
            {
                "type": "move",
                "game_id": event.game_id,
                "move_number": event.move_number,
                "color": event.color,
                "move_uci": event.move_uci,
                "move_san": event.move_san,
                "fen": event.fen,
                "eval_cp": event.eval_cp,
                "eval_mate": event.eval_mate,
                "best_move_san": event.best_move_san,
                "cpl": event.cpl,
                "classification": event.classification,
                "win_pct_white": event.win_pct_white,
                "accuracy": event.accuracy,
                "think_time_ms": event.think_time_ms,
                "illegal_attempts": event.illegal_attempts,
                "white_avg_cpl": event.white_avg_cpl,
                "black_avg_cpl": event.black_avg_cpl,
                "pgn_so_far": event.pgn_so_far,
            }
        )

    async def _emit(self, payload: dict[str, Any]) -> None:
        if self.event_callback is None:
            return
        await self.event_callback(payload)

    def _ensure_players(self, session: Session) -> dict[str, int]:
        rows: dict[str, int] = {}
        for adapter in self.players:
            name = adapter.get_name()
            row = session.exec(select(Player).where(Player.name == name)).first()
            descriptor = self.player_descriptors.get(name, {})
            provider = descriptor.get("provider", "unknown")
            model_id = descriptor.get("model", "unknown")

            if row is None:
                row = Player(name=name, provider=provider, model_id=model_id)
                session.add(row)
                session.flush()
            else:
                row.provider = provider
                row.model_id = model_id

            if row.id is None:
                raise RuntimeError(f"Player '{name}' did not receive a database ID")
            rows[name] = row.id

        session.commit()
        return rows

    def _next_game_id(self, session: Session) -> int:
        max_id = session.exec(select(func.max(Game.id))).one()
        if max_id is None:
            return 1
        return int(max_id) + 1

    def _abandon_game(self, session: Session, game_id: int) -> None:
        """Mark an in-progress game as abandoned."""
        game = session.get(Game, game_id)
        if game and game.status == "in_progress":
            game.status = "abandoned"

    def _apply_player_result(
        self,
        player: Player,
        result: str,
        as_white: bool,
        avg_cpl: float,
        accuracy: float,
        tokens: int,
        cost: float,
        blunders: int,
    ) -> None:
        old_games = player.games_played
        player.games_played += 1

        if result == "1/2-1/2":
            player.draws += 1
        elif (result == "1-0" and as_white) or (result == "0-1" and not as_white):
            player.wins += 1
        else:
            player.losses += 1

        player.avg_cpl = self._running_avg(player.avg_cpl, old_games, avg_cpl)
        player.avg_accuracy = self._running_avg(player.avg_accuracy, old_games, accuracy)
        player.total_tokens += int(tokens)
        player.total_cost_usd += float(cost)
        player.total_blunders += int(blunders)

    @staticmethod
    def _running_avg(current_avg: float, current_n: int, new_value: float) -> float:
        if current_n <= 0:
            return float(new_value)
        return ((current_avg * current_n) + float(new_value)) / (current_n + 1)

    def get_standings(
        self,
        session: Session | None = None,
    ) -> list[dict[str, Any]]:
        should_close = session is None
        if session is None:
            session = self.session_factory()

        try:
            players = session.exec(select(Player)).all()

            standings: list[dict[str, Any]] = []
            for player in players:
                if _is_benchmark_anchor_row(player):
                    continue

                blunder_rate = player.total_blunders / max(player.games_played, 1)

                standings.append(
                    {
                        "name": player.name,
                        "elo": round(player.elo, 1),
                        "elo_white": round(player.elo_white, 1),
                        "elo_black": round(player.elo_black, 1),
                        "elo_confidence": player.elo_confidence,
                        "elo_white_confidence": player.elo_white_confidence,
                        "elo_black_confidence": player.elo_black_confidence,
                        "elo_white_qualifying_moves": player.elo_white_qualifying_moves,
                        "elo_black_qualifying_moves": player.elo_black_qualifying_moves,
                        "wins": player.wins,
                        "losses": player.losses,
                        "draws": player.draws,
                        "avg_accuracy": round(player.avg_accuracy, 1),
                        "avg_cpl": round(player.avg_cpl, 1),
                        "blunder_rate": round(blunder_rate, 2),
                        "total_cost_usd": round(player.total_cost_usd, 4),
                    }
                )

            standings.sort(key=lambda row: (-row["elo"], row["name"]))
            return standings
        finally:
            if should_close:
                session.close()

    def get_player_by_name(self, session: Session, player_name: str) -> Player | None:
        return session.exec(select(Player).where(Player.name == player_name)).first()

    @staticmethod
    def cleanup_players(players: list[PlayerAdapter]) -> None:
        for player in players:
            cleanup = getattr(player, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass
