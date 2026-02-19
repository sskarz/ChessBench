from __future__ import annotations

import argparse
import asyncio
import json
import os

from src.analysis.analyzer import StockfishAnalyzer
from src.game.orchestrator import GameConfig, GameOrchestrator
from src.players.engine_player import UCIEnginePlayer


async def _run(args: argparse.Namespace) -> None:
    analyzer = StockfishAnalyzer(
        engine_path=args.stockfish_path,
        depth=args.depth,
        threads=args.threads,
        hash_mb=args.hash_mb,
    )
    white = UCIEnginePlayer("Stockfish-White", args.stockfish_path, time_limit=args.time_limit)
    black = UCIEnginePlayer("Stockfish-Black", args.stockfish_path, time_limit=args.time_limit)
    orchestrator = GameOrchestrator(
        analyzer=analyzer,
        config=GameConfig(max_moves=args.max_moves, move_delay_seconds=args.move_delay),
    )

    try:
        result = await orchestrator.play_game(game_id=1, white=white, black=black)
        print(json.dumps(result, indent=2))
    finally:
        white.cleanup()
        black.cleanup()
        analyzer.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stockfish vs Stockfish")
    parser.add_argument("--stockfish-path", default=os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish"))
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hash-mb", type=int, default=128)
    parser.add_argument("--time-limit", type=float, default=0.2)
    parser.add_argument("--max-moves", type=int, default=80)
    parser.add_argument("--move-delay", type=float, default=0.0)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
