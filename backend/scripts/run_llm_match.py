from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os

from src.analysis.analyzer import StockfishAnalyzer
from src.game.orchestrator import GameConfig, GameOrchestrator
from src.players.llm_player import LLMPlayer

logger = logging.getLogger(__name__)


def _resolve_openrouter_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if key:
        return key

    for deprecated_key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        fallback = os.getenv(deprecated_key, "").strip()
        if not fallback:
            continue
        logger.warning(
            "OPENROUTER_API_KEY is not set. Using deprecated fallback %s; set OPENROUTER_API_KEY instead.",
            deprecated_key,
        )
        return fallback

    return ""


def _build_llm_player(
    name: str,
    provider: str,
    model: str,
    retries: int,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str,
) -> LLMPlayer:
    if provider != "openrouter":
        raise ValueError(f"Unsupported provider: {provider}")

    api_key = _resolve_openrouter_api_key()
    if not api_key:
        raise RuntimeError("Missing API key. Set OPENROUTER_API_KEY.")

    return LLMPlayer(
        name=name,
        provider=provider,
        model=model,
        api_key=api_key,
        max_retries=retries,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        http_referer=os.getenv("OPENROUTER_HTTP_REFERER", ""),
        x_title=os.getenv("OPENROUTER_X_TITLE", "ChessBench"),
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
        max_tokens=args.max_tokens,
        reasoning_effort=args.reasoning_effort,
    )
    black = _build_llm_player(
        name=args.black_name,
        provider=args.black_provider,
        model=args.black_model,
        retries=args.max_retries,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        reasoning_effort=args.reasoning_effort,
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
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run LLM vs LLM")
    parser.add_argument("--stockfish-path", default=os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish"))
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hash-mb", type=int, default=128)
    parser.add_argument("--max-moves", type=int, default=80)
    parser.add_argument("--move-delay", type=float, default=0.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=int(os.getenv("LLM_MAX_TOKENS", "128")))
    parser.add_argument("--reasoning-effort", default=os.getenv("LLM_REASONING_EFFORT", ""))

    parser.add_argument("--white-name", default="GPT")
    parser.add_argument("--white-provider", choices=["openrouter"], default="openrouter")
    parser.add_argument("--white-model", default="openai/gpt-4o")

    parser.add_argument("--black-name", default="Claude Sonnet")
    parser.add_argument("--black-provider", choices=["openrouter"], default="openrouter")
    parser.add_argument("--black-model", default="anthropic/claude-sonnet-4")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
