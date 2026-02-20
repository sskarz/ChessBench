from __future__ import annotations

import asyncio
import itertools
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import Session, select

from src.db.models import Game, MoveAnalysis, Player, Tournament
from src.game.orchestrator import GameOrchestrator, LiveMoveEvent, ResumeState
from src.players.base import PlayerAdapter

logger = logging.getLogger(__name__)

TournamentEventCallback = Callable[[dict[str, Any]], Awaitable[None]]
SessionFactory = Callable[[], Session]


class EloCalculator:
    K = 32

    @staticmethod
    def expected_score(rating_a: float, rating_b: float) -> float:
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    @staticmethod
    def update(rating: float, expected: float, actual: float) -> float:
        return rating + EloCalculator.K * (actual - expected)


def _generate_pairing_schedule(
    num_players: int, rounds: int
) -> list[tuple[int, int, int, int]]:
    """Generate a deterministic flat list of (round_number, pairing_index, white_idx, black_idx)."""
    pairings = list(itertools.combinations(range(num_players), 2))
    schedule: list[tuple[int, int, int, int]] = []
    idx = 0
    for round_number in range(1, rounds + 1):
        for i, j in pairings:
            for w_idx, b_idx in ((i, j), (j, i)):
                schedule.append((round_number, idx, w_idx, b_idx))
                idx += 1
    return schedule


class TournamentManager:
    def __init__(
        self,
        players: list[PlayerAdapter],
        orchestrator: GameOrchestrator,
        session_factory: SessionFactory,
        event_callback: TournamentEventCallback | None = None,
        rounds: int = 1,
        player_descriptors: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.players = players
        self.orchestrator = orchestrator
        self.session_factory = session_factory
        self.event_callback = event_callback
        self.rounds = rounds
        self.player_descriptors = player_descriptors or {}
        self._run_lock = asyncio.Lock()

    async def run_round_robin(self, rounds: int | None = None) -> dict[str, Any]:
        if self._run_lock.locked():
            raise RuntimeError("Tournament is already running")

        async with self._run_lock:
            rounds_to_run = rounds if rounds is not None else self.rounds
            if rounds_to_run < 1:
                raise ValueError("rounds must be >= 1")

            with self.session_factory() as session:
                player_ids = self._ensure_players(session)
                next_game_id = self._next_game_id(session)

            player_names = [p.get_name() for p in self.players]
            schedule = _generate_pairing_schedule(len(self.players), rounds_to_run)

            # Create tournament record
            with self.session_factory() as session:
                tournament = Tournament(
                    name=f"Round Robin {datetime.utcnow().isoformat()}",
                    format="round_robin",
                    rounds=rounds_to_run,
                    status="running",
                    player_names_json=json.dumps(player_names),
                )
                session.add(tournament)
                session.commit()
                session.refresh(tournament)
                tournament_id = tournament.id

            games_played = 0

            try:
                for round_number, pairing_idx, w_idx, b_idx in schedule:
                    white = self.players[w_idx]
                    black = self.players[b_idx]
                    game_id = next_game_id
                    next_game_id += 1

                    # Create in-progress Game record before playing
                    with self.session_factory() as session:
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

                    await self._emit(
                        {
                            "type": "game_start",
                            "game_id": game_id,
                            "white": white.get_name(),
                            "black": black.get_name(),
                            "round": round_number,
                        }
                    )

                    self.orchestrator.event_callback = self._on_move_event
                    self.orchestrator.on_move_recorded = self._persist_move
                    started_at = datetime.utcnow()
                    result = await self.orchestrator.play_game(game_id=game_id, white=white, black=black)
                    completed_at = datetime.utcnow()

                    with self.session_factory() as session:
                        self._finalize_game(
                            session=session,
                            game_id=game_id,
                            game_result=result,
                            white_player_id=player_ids[white.get_name()],
                            black_player_id=player_ids[black.get_name()],
                            started_at=started_at,
                            completed_at=completed_at,
                        )
                        session.commit()
                        standings = self.get_standings(session=session)

                    await self._emit(
                        {
                            "type": "game_end",
                            "game_id": game_id,
                            "result": result["result"],
                            "termination": result["termination"],
                            "white_accuracy": result["white_accuracy"],
                            "black_accuracy": result["black_accuracy"],
                            "standings": standings,
                        }
                    )
                    games_played += 1

                # Mark tournament completed
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
                        t.error_message = "Tournament interrupted"
                    session.commit()
                raise

            return {
                "games_played": games_played,
                "standings": final_standings,
            }

    async def resume_round_robin(self, tournament_id: int) -> dict[str, Any]:
        """Resume an interrupted tournament from its last known state."""
        if self._run_lock.locked():
            raise RuntimeError("Tournament is already running")

        async with self._run_lock:
            with self.session_factory() as session:
                tournament = session.get(Tournament, tournament_id)
                if tournament is None:
                    raise ValueError(f"Tournament {tournament_id} not found")

                stored_names: list[str] = json.loads(tournament.player_names_json)
                rounds_to_run = tournament.rounds

                player_ids = self._ensure_players(session)

            # Validate current roster matches stored order
            current_names = {p.get_name() for p in self.players}
            for name in stored_names:
                if name not in current_names:
                    raise ValueError(f"Player '{name}' from tournament not available in current roster")

            # Reorder players to match stored order
            player_map = {p.get_name(): p for p in self.players}
            ordered_players = [player_map[name] for name in stored_names]

            schedule = _generate_pairing_schedule(len(ordered_players), rounds_to_run)

            # Find completed and in-progress games
            with self.session_factory() as session:
                completed_games = session.exec(
                    select(Game).where(
                        Game.tournament_id == tournament_id,
                        Game.status == "completed",
                    )
                ).all()
                completed_indices = {g.pairing_index for g in completed_games}

                in_progress_game = session.exec(
                    select(Game).where(
                        Game.tournament_id == tournament_id,
                        Game.status == "in_progress",
                    )
                ).first()

                in_progress_pairing_idx: int | None = None
                resume_state: ResumeState | None = None
                resume_game_id: int | None = None

                if in_progress_game:
                    in_progress_pairing_idx = in_progress_game.pairing_index
                    resume_game_id = in_progress_game.id
                    resume_state = self._build_resume_state(session, in_progress_game.id)

                next_game_id = self._next_game_id(session)

                # Update tournament status
                tournament = session.get(Tournament, tournament_id)
                if tournament:
                    tournament.status = "running"
                    tournament.error_message = None
                session.commit()

            games_played = 0

            try:
                for round_number, pairing_idx, w_idx, b_idx in schedule:
                    # Skip completed games
                    if pairing_idx in completed_indices:
                        continue

                    white = ordered_players[w_idx]
                    black = ordered_players[b_idx]

                    # Resume in-progress game or create new one
                    if pairing_idx == in_progress_pairing_idx and resume_game_id is not None:
                        game_id = resume_game_id
                    else:
                        # Abandon any stale in-progress game for this pairing
                        game_id = next_game_id
                        next_game_id += 1

                        with self.session_factory() as session:
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

                    await self._emit(
                        {
                            "type": "game_start",
                            "game_id": game_id,
                            "white": white.get_name(),
                            "black": black.get_name(),
                            "round": round_number,
                        }
                    )

                    self.orchestrator.event_callback = self._on_move_event
                    self.orchestrator.on_move_recorded = self._persist_move

                    started_at = datetime.utcnow()
                    current_resume = resume_state if pairing_idx == in_progress_pairing_idx else None
                    result = await self.orchestrator.play_game(
                        game_id=game_id,
                        white=white,
                        black=black,
                        resume=current_resume,
                    )
                    completed_at = datetime.utcnow()

                    with self.session_factory() as session:
                        self._finalize_game(
                            session=session,
                            game_id=game_id,
                            game_result=result,
                            white_player_id=player_ids[white.get_name()],
                            black_player_id=player_ids[black.get_name()],
                            started_at=started_at,
                            completed_at=completed_at,
                        )
                        session.commit()
                        standings = self.get_standings(session=session)

                    await self._emit(
                        {
                            "type": "game_end",
                            "game_id": game_id,
                            "result": result["result"],
                            "termination": result["termination"],
                            "white_accuracy": result["white_accuracy"],
                            "black_accuracy": result["black_accuracy"],
                            "standings": standings,
                        }
                    )
                    games_played += 1

                    # Clear resume state after first game processed
                    if pairing_idx == in_progress_pairing_idx:
                        in_progress_pairing_idx = None
                        resume_state = None
                        resume_game_id = None

                # Mark tournament completed
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
                        t.error_message = "Tournament interrupted during resume"
                    session.commit()
                raise

            return {
                "games_played": games_played,
                "standings": final_standings,
            }

    def _build_resume_state(self, session: Session, game_id: int) -> ResumeState:
        """Build a ResumeState from persisted MoveAnalysis rows."""
        rows = session.exec(
            select(MoveAnalysis)
            .where(MoveAnalysis.game_id == game_id)
            .order_by(MoveAnalysis.id)
        ).all()

        state = ResumeState()
        for row in rows:
            state.moves_uci.append(row.move_uci)
            if row.color == "white":
                state.white_cpls.append(row.centipawn_loss)
                state.white_illegals += row.illegal_attempts
                state.white_tokens += row.tokens_used or 0
            else:
                state.black_cpls.append(row.centipawn_loss)
                state.black_illegals += row.illegal_attempts
                state.black_tokens += row.tokens_used or 0
            state.analysis_records.append({
                "game_id": row.game_id,
                "move_number": row.move_number,
                "color": row.color,
                "move_uci": row.move_uci,
                "move_san": row.move_san,
                "fen_before": row.fen_before,
                "fen_after": row.fen_after,
                "eval_before_cp": row.eval_before_cp,
                "eval_after_cp": row.eval_after_cp,
                "best_move_uci": row.best_move_uci,
                "best_move_san": row.best_move_san,
                "centipawn_loss": row.centipawn_loss,
                "classification": row.classification,
                "think_time_ms": row.think_time_ms,
                "tokens_used": row.tokens_used,
                "illegal_attempts": row.illegal_attempts,
            })
        return state

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
        """Update an existing in-progress Game row with final stats and update Player records."""
        white_row = session.get(Player, white_player_id)
        black_row = session.get(Player, black_player_id)
        if white_row is None or black_row is None:
            raise RuntimeError("Missing player row while saving game")

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

        self._apply_player_result(
            player=white_row,
            result=game_result["result"],
            as_white=True,
            avg_cpl=game_result["white_avg_cpl"],
            accuracy=game_result["white_accuracy"],
            tokens=game_result["white_tokens"],
            cost=game_result["white_cost_usd"],
        )
        self._apply_player_result(
            player=black_row,
            result=game_result["result"],
            as_white=False,
            avg_cpl=game_result["black_avg_cpl"],
            accuracy=game_result["black_accuracy"],
            tokens=game_result["black_tokens"],
            cost=game_result["black_cost_usd"],
        )

        self._update_elo(white_row, black_row, game_result["result"])

    def _save_game_and_updates(
        self,
        session: Session,
        game_result: dict[str, Any],
        white_player_id: int,
        black_player_id: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        """Legacy method kept for backward compatibility with existing tests."""
        white_row = session.get(Player, white_player_id)
        black_row = session.get(Player, black_player_id)
        if white_row is None or black_row is None:
            raise RuntimeError("Missing player row while saving game")

        game = Game(
            id=game_result["game_id"],
            white_id=white_row.id,
            black_id=black_row.id,
            status="completed",
            result=game_result["result"],
            termination=game_result["termination"],
            pgn=game_result["pgn"],
            moves_count=game_result["moves_count"],
            white_avg_cpl=game_result["white_avg_cpl"],
            black_avg_cpl=game_result["black_avg_cpl"],
            white_accuracy=game_result["white_accuracy"],
            black_accuracy=game_result["black_accuracy"],
            white_blunders=game_result["white_blunders"],
            black_blunders=game_result["black_blunders"],
            white_mistakes=game_result["white_mistakes"],
            black_mistakes=game_result["black_mistakes"],
            white_illegal_attempts=game_result["white_illegal_attempts"],
            black_illegal_attempts=game_result["black_illegal_attempts"],
            white_tokens=game_result["white_tokens"],
            black_tokens=game_result["black_tokens"],
            white_cost_usd=game_result["white_cost_usd"],
            black_cost_usd=game_result["black_cost_usd"],
            duration_seconds=game_result["duration_seconds"],
            opening_name=game_result.get("opening_name"),
            opening_eco=game_result.get("opening_eco"),
            started_at=started_at,
            completed_at=completed_at,
        )
        session.add(game)

        for raw in game_result["move_analyses"]:
            session.add(
                MoveAnalysis(
                    game_id=game_result["game_id"],
                    move_number=raw["move_number"],
                    color=raw["color"],
                    move_uci=raw["move_uci"],
                    move_san=raw["move_san"],
                    fen_before=raw["fen_before"],
                    fen_after=raw["fen_after"],
                    eval_before_cp=raw["eval_before_cp"],
                    eval_after_cp=raw["eval_after_cp"],
                    best_move_uci=raw["best_move_uci"],
                    best_move_san=raw["best_move_san"],
                    centipawn_loss=raw["centipawn_loss"],
                    classification=raw["classification"],
                    think_time_ms=raw["think_time_ms"],
                    tokens_used=raw["tokens_used"],
                    illegal_attempts=raw["illegal_attempts"],
                )
            )

        self._apply_player_result(
            player=white_row,
            result=game_result["result"],
            as_white=True,
            avg_cpl=game_result["white_avg_cpl"],
            accuracy=game_result["white_accuracy"],
            tokens=game_result["white_tokens"],
            cost=game_result["white_cost_usd"],
        )
        self._apply_player_result(
            player=black_row,
            result=game_result["result"],
            as_white=False,
            avg_cpl=game_result["black_avg_cpl"],
            accuracy=game_result["black_accuracy"],
            tokens=game_result["black_tokens"],
            cost=game_result["black_cost_usd"],
        )

        self._update_elo(white_row, black_row, game_result["result"])

    def _abandon_game(self, session: Session, game_id: int) -> None:
        """Mark an in-progress game as abandoned."""
        game = session.get(Game, game_id)
        if game and game.status == "in_progress":
            game.status = "abandoned"

    def _update_elo(self, white: Player, black: Player, result: str) -> None:
        expected_white = EloCalculator.expected_score(white.elo, black.elo)
        expected_black = 1 - expected_white

        if result == "1-0":
            actual_white, actual_black = 1.0, 0.0
        elif result == "0-1":
            actual_white, actual_black = 0.0, 1.0
        else:
            actual_white, actual_black = 0.5, 0.5

        white.elo = EloCalculator.update(white.elo, expected_white, actual_white)
        black.elo = EloCalculator.update(black.elo, expected_black, actual_black)

    def _apply_player_result(
        self,
        player: Player,
        result: str,
        as_white: bool,
        avg_cpl: float,
        accuracy: float,
        tokens: int,
        cost: float,
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

    @staticmethod
    def _running_avg(current_avg: float, current_n: int, new_value: float) -> float:
        if current_n <= 0:
            return float(new_value)
        return ((current_avg * current_n) + float(new_value)) / (current_n + 1)

    def get_standings(self, session: Session | None = None) -> list[dict[str, Any]]:
        should_close = session is None
        if session is None:
            session = self.session_factory()

        try:
            players = session.exec(select(Player)).all()
            standings: list[dict[str, Any]] = []
            for player in players:
                games = session.exec(
                    select(Game).where(
                        or_(Game.white_id == player.id, Game.black_id == player.id),
                        Game.status == "completed",
                    )
                ).all()
                blunders = sum(
                    g.white_blunders if g.white_id == player.id else g.black_blunders
                    for g in games
                )
                blunder_rate = blunders / max(len(games), 1)

                standings.append(
                    {
                        "name": player.name,
                        "elo": round(player.elo, 1),
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
