from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Any

from src.analysis.analyzer import StockfishAnalyzer
from src.config import Settings
from src.game.orchestrator import GameConfig, GameOrchestrator, ResumeState
from src.players.base import PlayerAdapter
from src.players.engine_player import UCIEnginePlayer

logger = logging.getLogger(__name__)

# Type aliases matching tournament.py
TournamentEventCallback = Any  # Callable[[dict], Awaitable[None]]
SessionFactory = Any  # Callable[[], Session]


class ParallelScheduler:
    """Runs tournament games concurrently, up to max_concurrent_games at once.

    Each concurrent game gets its own StockfishAnalyzer and GameOrchestrator.
    UCIEnginePlayers are cloned per-game; LLMPlayers are reused (thread-safe HTTP client).
    """

    def __init__(
        self,
        players: list[PlayerAdapter],
        player_ids: dict[str, int],
        tournament_id: int,
        session_factory: SessionFactory,
        event_callback: TournamentEventCallback | None,
        settings: Settings,
        player_descriptors: dict[str, dict[str, str]],
        persist_move: Any,
        on_move_event: Any,
        finalize_game: Any,
        get_standings: Any,
        abandon_game: Any,
    ) -> None:
        self.players = players
        self.player_ids = player_ids
        self.tournament_id = tournament_id
        self.session_factory = session_factory
        self.event_callback = event_callback
        self.settings = settings
        self.player_descriptors = player_descriptors
        self._persist_move = persist_move
        self._on_move_event = on_move_event
        self._finalize_game = finalize_game
        self._get_standings = get_standings
        self._abandon_game = abandon_game

        self._elo_lock = asyncio.Lock()

        max_cg = settings.max_concurrent_games
        self._max_concurrent = max_cg if max_cg > 0 else max(1, len(players) // 2)

    async def run_schedule(
        self,
        schedule: list[tuple[int, int, int, int]],
        pre_allocated_game_ids: dict[int, int],
        completed_indices: set[int] | None = None,
        resume_states: dict[int, ResumeState] | None = None,
        allow_concurrent_players: bool = False,
    ) -> int:
        """Execute pairings with up to max_concurrent_games in parallel.

        Returns the number of games played.
        """
        completed_indices = completed_indices or set()
        resume_states = resume_states or {}

        # Build pending queue, skipping completed
        pending: deque[tuple[int, int, int, int]] = deque()
        for entry in schedule:
            _, pairing_idx, _, _ = entry
            if pairing_idx not in completed_indices:
                pending.append(entry)

        busy_players: set[int] = set()  # player indices currently in a game
        active_tasks: dict[asyncio.Task, tuple[int, int, int, int, datetime, list[Any]]] = {}
        games_played = 0

        try:
            while pending or active_tasks:
                # LAUNCH phase: start new games where both players are free
                launched = 0
                to_launch: list[tuple[int, int, int, int]] = []
                remaining: deque[tuple[int, int, int, int]] = deque()

                for entry in pending:
                    round_number, pairing_idx, w_idx, b_idx = entry
                    if len(active_tasks) + launched >= self._max_concurrent:
                        remaining.append(entry)
                    elif allow_concurrent_players or (
                        w_idx not in busy_players and b_idx not in busy_players
                    ):
                        to_launch.append(entry)
                        if not allow_concurrent_players:
                            busy_players.add(w_idx)
                            busy_players.add(b_idx)
                        launched += 1
                    else:
                        remaining.append(entry)

                pending = remaining

                for entry in to_launch:
                    round_number, pairing_idx, w_idx, b_idx = entry
                    game_id = pre_allocated_game_ids[pairing_idx]

                    # Resolve players - clone engines for concurrency safety
                    white = self._resolve_player(w_idx)
                    black = self._resolve_player(b_idx)

                    # Create per-game analyzer and orchestrator
                    analyzer = StockfishAnalyzer(
                        engine_path=self.settings.stockfish_path,
                        depth=self.settings.analysis_depth,
                        threads=self.settings.stockfish_threads,
                        hash_mb=self.settings.stockfish_hash_mb,
                    )
                    orchestrator = GameOrchestrator(
                        analyzer=analyzer,
                        event_callback=self._on_move_event,
                        config=GameConfig(
                            max_moves=self.settings.max_moves_per_side,
                            analyze_depth=self.settings.analysis_depth,
                            move_delay_seconds=self.settings.move_delay_seconds,
                        ),
                    )
                    orchestrator.on_move_recorded = self._persist_move

                    # Emit game_start
                    await self._emit({
                        "type": "game_start",
                        "game_id": game_id,
                        "white": white.get_name(),
                        "black": black.get_name(),
                        "round": round_number,
                    })

                    # Restore partial game state for this pairing when available.
                    current_resume = resume_states.get(pairing_idx)
                    started_at = datetime.utcnow()

                    # Track per-game resources for cleanup: [analyzer, white_clone_or_None, black_clone_or_None]
                    resources: list[Any] = [analyzer]
                    resources.append(white if isinstance(self.players[w_idx], UCIEnginePlayer) else None)
                    resources.append(black if isinstance(self.players[b_idx], UCIEnginePlayer) else None)

                    task = asyncio.create_task(
                        self._play_single_game(
                            orchestrator=orchestrator,
                            game_id=game_id,
                            white=white,
                            black=black,
                            resume=current_resume,
                        ),
                        name=f"game-{game_id}",
                    )
                    active_tasks[task] = (round_number, pairing_idx, w_idx, b_idx, started_at, resources)

                if not active_tasks:
                    break

                # WAIT phase: wait for at least one game to complete
                done, _ = await asyncio.wait(
                    active_tasks.keys(), return_when=asyncio.FIRST_COMPLETED
                )

                # COLLECT phase: process completed games
                for task in done:
                    round_number, pairing_idx, w_idx, b_idx, started_at, resources = active_tasks.pop(task)
                    analyzer_ref = resources[0]
                    cloned_white = resources[1]
                    cloned_black = resources[2]

                    try:
                        game_result = task.result()
                        game_id = pre_allocated_game_ids[pairing_idx]
                        white_name = self.players[w_idx].get_name()
                        black_name = self.players[b_idx].get_name()

                        # Finalize under lock to serialize Elo updates
                        async with self._elo_lock:
                            completed_at = datetime.utcnow()
                            with self.session_factory() as session:
                                self._finalize_game(
                                    session=session,
                                    game_id=game_id,
                                    game_result=game_result,
                                    white_player_id=self.player_ids[white_name],
                                    black_player_id=self.player_ids[black_name],
                                    started_at=started_at,
                                    completed_at=completed_at,
                                )
                                session.commit()
                                standings = self._get_standings(session=session)

                        await self._emit({
                            "type": "game_end",
                            "game_id": game_id,
                            "result": game_result["result"],
                            "termination": game_result["termination"],
                            "white_accuracy": game_result["white_accuracy"],
                            "black_accuracy": game_result["black_accuracy"],
                            "standings": standings,
                        })
                        games_played += 1

                    except Exception:
                        game_id = pre_allocated_game_ids[pairing_idx]
                        logger.exception("Game %d failed", game_id)
                        # Mark game as abandoned
                        try:
                            with self.session_factory() as session:
                                self._abandon_game(session, game_id)
                                session.commit()
                                standings = self._get_standings(session=session)

                            await self._emit({
                                "type": "game_end",
                                "game_id": game_id,
                                "result": "*",
                                "termination": "error",
                                "white_accuracy": 0,
                                "black_accuracy": 0,
                                "standings": standings,
                            })
                        except Exception:
                            logger.exception("Failed to abandon game %d", game_id)

                    finally:
                        # Cleanup per-game resources
                        if not allow_concurrent_players:
                            busy_players.discard(w_idx)
                            busy_players.discard(b_idx)
                        try:
                            analyzer_ref.shutdown()
                        except Exception:
                            pass
                        if cloned_white is not None:
                            try:
                                cloned_white.cleanup()
                            except Exception:
                                pass
                        if cloned_black is not None:
                            try:
                                cloned_black.cleanup()
                            except Exception:
                                pass

        except asyncio.CancelledError:
            # Tournament cancelled - clean up all active tasks
            for task in active_tasks:
                task.cancel()
            if active_tasks:
                await asyncio.gather(*active_tasks.keys(), return_exceptions=True)
            for task, (_, pairing_idx, w_idx, b_idx, _started_at, resources) in active_tasks.items():
                analyzer_ref = resources[0]
                cloned_white = resources[1]
                cloned_black = resources[2]
                try:
                    analyzer_ref.shutdown()
                except Exception:
                    pass
                if cloned_white is not None:
                    try:
                        cloned_white.cleanup()
                    except Exception:
                        pass
                if cloned_black is not None:
                    try:
                        cloned_black.cleanup()
                    except Exception:
                        pass
                # Mark in-progress games as abandoned
                game_id = pre_allocated_game_ids[pairing_idx]
                try:
                    with self.session_factory() as session:
                        self._abandon_game(session, game_id)
                        session.commit()
                except Exception:
                    pass
            raise

        return games_played

    def _resolve_player(self, player_idx: int) -> PlayerAdapter:
        """Return a player adapter suitable for a concurrent game.

        Clones UCIEnginePlayer instances (they hold a single engine process).
        LLMPlayer instances are reused (thread-safe HTTP client).
        """
        player = self.players[player_idx]
        if isinstance(player, UCIEnginePlayer):
            return player.clone()
        return player

    async def _play_single_game(
        self,
        orchestrator: GameOrchestrator,
        game_id: int,
        white: PlayerAdapter,
        black: PlayerAdapter,
        resume: ResumeState | None = None,
    ) -> dict[str, Any]:
        return await orchestrator.play_game(
            game_id=game_id,
            white=white,
            black=black,
            resume=resume,
        )

    async def _emit(self, payload: dict[str, Any]) -> None:
        if self.event_callback is None:
            return
        await self.event_callback(payload)
