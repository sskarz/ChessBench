from __future__ import annotations

import argparse
import asyncio
import json
import os

from src.analysis.analyzer import StockfishAnalyzer
from src.game.orchestrator import GameConfig, GameOrchestrator
from src.players.llm_player import LLMPlayer


def _key_for_provider(provider: str) -> str:
    mapping = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    try:
        return mapping[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {provider}") from exc


def _build_llm_player(name: str, provider: str, model: str, retries: int, temperature: float) -> LLMPlayer:
    key_env = _key_for_provider(provider)
    api_key = os.getenv(key_env, "")
    if not api_key:
        raise RuntimeError(f"Missing API key in env var: {key_env}")

    return LLMPlayer(
        name=name,
        provider=provider,
        model=model,
        api_key=api_key,
        max_retries=retries,
        temperature=temperature,
    )


async def _run(args: argparse.Namespace) -> None:
    analyzer = StockfishAnalyzer(
        engine_path=args.stockfish_path,
        depth=args.depth,
        threads=args.threads,
        hash_mb=args.hash_mb,
    )
    white = _build_llm_player(
        name=args.white_name,
        provider=args.white_provider,
        model=args.white_model,
        retries=args.max_retries,
        temperature=args.temperature,
    )
    black = _build_llm_player(
        name=args.black_name,
        provider=args.black_provider,
        model=args.black_model,
        retries=args.max_retries,
        temperature=args.temperature,
    )

    orchestrator = GameOrchestrator(
        analyzer=analyzer,
        config=GameConfig(max_moves=args.max_moves, move_delay_seconds=args.move_delay),
    )

    try:
        result = await orchestrator.play_game(game_id=1, white=white, black=black)
        print(json.dumps(result, indent=2))
    finally:
        analyzer.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM vs LLM")
    parser.add_argument("--stockfish-path", default=os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish"))
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hash-mb", type=int, default=128)
    parser.add_argument("--max-moves", type=int, default=80)
    parser.add_argument("--move-delay", type=float, default=0.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.0)

    parser.add_argument("--white-name", default="GPT-4o")
    parser.add_argument("--white-provider", choices=["openai", "anthropic", "google"], default="openai")
    parser.add_argument("--white-model", default="gpt-4o")

    parser.add_argument("--black-name", default="Claude Sonnet")
    parser.add_argument("--black-provider", choices=["openai", "anthropic", "google"], default="anthropic")
    parser.add_argument("--black-model", default="claude-sonnet-4-5-20250929")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
