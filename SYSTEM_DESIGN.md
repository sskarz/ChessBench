# LLM Chess Arena — System Design

A platform where LLMs play chess against each other in continuous tournaments, viewable in real time on the web, with deep analytics powered by Stockfish.

---

## 1. Product Vision

Spectators open a URL and see a live chess game between, say, Claude Sonnet and GPT-4o. Pieces animate on an interactive board. A sidebar shows the Stockfish evaluation bar shifting after each move, centipawn loss per move, blunder annotations, and a running move-by-move accuracy chart. Below the board sits a tournament scoreboard with Elo ratings, win/loss/draw records, average centipawn loss, blunder rates, and cost-per-game for each model. Completed games are browsable with full Stockfish post-game analysis.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                         │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │  Live Board   │  │  Scoreboard  │  │  Game Archive / Replay    │ │
│  │  (react-      │  │  (Elo, W/L/D │  │  (Full analysis, move     │ │
│  │  chessboard)  │  │  accuracy)   │  │   accuracy graphs)        │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────────┘ │
│         └──────────────────┴──────────────────────┘                 │
│                            │ WebSocket + REST                       │
└────────────────────────────┼────────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                      API SERVER (FastAPI)                            │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  WebSocket    │  │  REST API    │  │  SSE / Event Stream      │  │
│  │  Manager      │  │  (standings, │  │  (live move broadcast)   │  │
│  │  (live moves) │  │  games, etc) │  │                          │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │
│         └──────────────────┴─────────────────────┘                  │
│                            │                                        │
│  ┌─────────────────────────▼──────────────────────────────────────┐ │
│  │                    EVENT BUS (in-process asyncio.Queue          │ │
│  │                    or Redis pub/sub for multi-process)          │ │
│  └─────────────────────────┬──────────────────────────────────────┘ │
└────────────────────────────┼────────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                     GAME ENGINE (Python)                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Tournament   │  │    Game      │  │   Stockfish Analyzer     │  │
│  │  Manager      │──│  Orchestrator│──│   (post-move eval,       │  │
│  │  (pairings,   │  │  (turn loop, │  │    CPL, blunders,        │  │
│  │   scheduling) │  │   clock)     │  │    best move comparison) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     Player Adapters                          │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │   │
│  │  │ OpenAI  │ │Anthropic│ │ Google  │ │Stockfish│ ...        │   │
│  │  │ (GPT-4o,│ │(Claude) │ │(Gemini) │ │(baseline│           │   │
│  │  │  o4-mini│ │         │ │         │ │  engine)│           │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                      DATA LAYER                                     │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  SQLite /     │  │  PGN Files   │  │  JSON Game Logs          │  │
│  │  PostgreSQL   │  │  (archive)   │  │  (per-move analysis)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

### Backend (Python)

| Package | Version | Purpose |
|---------|---------|---------|
| `python-chess` | 1.11+ | Board state, move validation, PGN, UCI engine comms |
| `stockfish` | 3.28+ | Python wrapper for Stockfish binary (analysis) |
| `fastapi` | 0.115+ | HTTP + WebSocket API server |
| `uvicorn` | 0.34+ | ASGI server |
| `openai` | 1.60+ | GPT-4o, o4-mini, gpt-3.5-turbo-instruct |
| `anthropic` | 0.42+ | Claude Sonnet, Claude Opus, Claude Haiku |
| `google-generativeai` | 0.8+ | Gemini 2.5 Pro, Gemini Flash |
| `sqlmodel` | 0.0.22+ | ORM for game/tournament data (SQLite or Postgres) |
| `pydantic` | 2.10+ | Data validation and serialization |

### Frontend (TypeScript)

| Package | Purpose |
|---------|---------|
| `next` (Next.js 15) | React framework, SSR, routing |
| `react-chessboard` | Interactive chessboard component (18K+ weekly npm downloads) |
| `chess.js` | Client-side move validation and PGN parsing |
| `recharts` or `chart.js` | Evaluation graphs, accuracy charts |
| `socket.io-client` or native WebSocket | Real-time move streaming |
| `tailwindcss` | Styling |

### Infrastructure

| Component | Purpose |
|-----------|---------|
| Stockfish 17 binary | Position evaluation and best-move analysis |
| SQLite (dev) / PostgreSQL (prod) | Persistent storage |
| Redis (optional) | Pub/sub for multi-worker scaling |
| Docker | Containerization and deployment |

---

## 4. Data Models

### Database Schema

```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)       # "claude-sonnet-4-5"
    provider: str                                      # "anthropic", "openai", "engine"
    model_id: str                                      # API model string
    elo: float = Field(default=1200.0)
    games_played: int = Field(default=0)
    wins: int = Field(default=0)
    losses: int = Field(default=0)
    draws: int = Field(default=0)
    avg_cpl: float = Field(default=0.0)                # avg centipawn loss
    avg_accuracy: float = Field(default=0.0)           # % accuracy (lichess-style)
    total_tokens: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tournament_id: int | None = Field(default=None, foreign_key="tournament.id")
    white_id: int = Field(foreign_key="player.id")
    black_id: int = Field(foreign_key="player.id")
    result: str                                        # "1-0", "0-1", "1/2-1/2"
    termination: str                                   # "checkmate", "stalemate", "resignation",
                                                       # "illegal_move_limit", "max_moves", "timeout"
    pgn: str                                           # Full PGN string
    moves_count: int
    white_avg_cpl: float                               # White's avg centipawn loss
    black_avg_cpl: float
    white_accuracy: float                              # Lichess-style accuracy %
    black_accuracy: float
    white_blunders: int                                # Moves with CPL > 200
    black_blunders: int
    white_mistakes: int                                # Moves with CPL > 100
    black_mistakes: int
    white_illegal_attempts: int                        # How many illegal moves before valid one
    black_illegal_attempts: int
    white_tokens: int                                  # Total API tokens consumed
    black_tokens: int
    white_cost_usd: float
    black_cost_usd: float
    duration_seconds: float
    opening_name: str | None = None                    # ECO opening name
    opening_eco: str | None = None                     # ECO code
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

class MoveAnalysis(SQLModel, table=True):
    """Per-move Stockfish analysis for every game."""
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    move_number: int                                   # 1-indexed full move number
    color: str                                         # "white" or "black"
    move_uci: str                                      # "e2e4"
    move_san: str                                      # "e4"
    fen_before: str                                    # Position before move
    fen_after: str                                     # Position after move
    eval_before_cp: int | None                         # Centipawn eval before (from white's POV)
    eval_after_cp: int | None                          # Centipawn eval after
    best_move_uci: str | None                          # Stockfish's best move
    best_move_san: str | None
    centipawn_loss: int                                # How much worse than best move
    classification: str                                # "best", "excellent", "good",
                                                       # "inaccuracy", "mistake", "blunder"
    is_book_move: bool = False
    think_time_ms: int | None = None                   # LLM response latency
    tokens_used: int | None = None                     # Tokens for this specific move
    illegal_attempts: int = 0                          # Retries before legal move

class Tournament(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    format: str                                        # "round_robin", "swiss", "match"
    rounds: int
    status: str = "pending"                            # "pending", "active", "completed"
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Move Classification Thresholds

These match Lichess's analysis conventions:

| Classification | Centipawn Loss Range | Color in UI |
|---------------|---------------------|-------------|
| Best move | 0 | Green ★ |
| Excellent | 1–10 | Green |
| Good | 11–30 | Light green |
| Inaccuracy | 31–100 | Yellow |
| Mistake | 101–200 | Orange |
| Blunder | 201+ | Red ?? |

**Accuracy formula** (Lichess-style, per-move):

```
accuracy(cpl) = 103.1668 * exp(-0.04354 * min(cpl, 1000)) - 3.1668
game_accuracy = mean(accuracy(cpl) for each move)
```

This maps CPL → a 0–100% score where 100% = always played the best move.

---

## 5. Component Design

### 5.1 Player Adapters

Every chess-playing entity implements a common interface. The key design decision: **send FEN + legal moves list** to chat models (not PGN completion), because modern chat models handle structured prompts better, and it makes illegal move recovery simpler.

```python
# src/players/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
import chess

@dataclass
class MoveResult:
    move: chess.Move
    tokens_used: int = 0
    cost_usd: float = 0.0
    think_time_ms: int = 0
    illegal_attempts: int = 0  # retries before producing legal move
    raw_response: str = ""     # for debugging

class PlayerAdapter(ABC):
    @abstractmethod
    def get_name(self) -> str: ...

    @abstractmethod
    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult: ...

    def on_game_start(self, color: chess.Color) -> None:
        """Called before game begins."""
        pass

    def on_game_end(self, result: str) -> None:
        """Called after game ends."""
        pass
```

#### LLM Player Implementation

```python
# src/players/llm_player.py
import time
import chess
from .base import PlayerAdapter, MoveResult

SYSTEM_PROMPT = """You are a chess grandmaster competing in a tournament.
Given the current board position (FEN notation) and the list of legal moves
available to you, choose the best move.

Rules:
- Respond with ONLY a single UCI-format move (e.g. "e2e4", "g1f3", "e7e8q")
- No explanations, no commentary, no formatting — just the move string
- The move MUST be from the legal moves list provided
- Think carefully about tactics, strategy, and positional advantage"""

class LLMPlayer(PlayerAdapter):
    def __init__(
        self,
        name: str,
        provider: str,            # "openai", "anthropic", "google"
        model: str,               # "gpt-4o", "claude-sonnet-4-5-20250929", etc.
        api_key: str,
        max_retries: int = 5,
        temperature: float = 0.0,
        max_tokens: int = 16,
    ):
        self.name = name
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = self._init_client()

    def _init_client(self):
        if self.provider == "openai":
            from openai import OpenAI
            return OpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            import anthropic
            return anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            return genai.GenerativeModel(self.model)

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        legal_moves = [m.uci() for m in board.legal_moves]
        fen = board.fen()

        total_tokens = 0
        total_cost = 0.0
        illegal_attempts = 0
        start_time = time.monotonic()

        user_msg = (
            f"Position (FEN): {fen}\n"
            f"Legal moves: {', '.join(legal_moves)}\n"
            f"Your color: {'White' if board.turn == chess.WHITE else 'Black'}\n"
            f"Move number: {board.fullmove_number}\n"
            f"Your move:"
        )

        for attempt in range(self.max_retries):
            raw_response, tokens, cost = self._call_api(SYSTEM_PROMPT, user_msg)
            total_tokens += tokens
            total_cost += cost

            move_str = raw_response.strip().lower().replace(" ", "")

            # Try parsing as UCI
            try:
                move = chess.Move.from_uci(move_str)
                if move in board.legal_moves:
                    return MoveResult(
                        move=move,
                        tokens_used=total_tokens,
                        cost_usd=total_cost,
                        think_time_ms=int((time.monotonic() - start_time) * 1000),
                        illegal_attempts=illegal_attempts,
                        raw_response=raw_response,
                    )
            except (ValueError, chess.InvalidMoveError):
                pass

            # Try parsing as SAN (some models return "Nf3" instead of "g1f3")
            try:
                move = board.parse_san(move_str)
                if move in board.legal_moves:
                    return MoveResult(
                        move=move,
                        tokens_used=total_tokens,
                        cost_usd=total_cost,
                        think_time_ms=int((time.monotonic() - start_time) * 1000),
                        illegal_attempts=illegal_attempts,
                        raw_response=raw_response,
                    )
            except (ValueError, chess.InvalidMoveError, chess.AmbiguousMoveError):
                pass

            illegal_attempts += 1
            user_msg = (
                f"'{raw_response.strip()}' is NOT a valid move.\n"
                f"You MUST respond with exactly one move from this list: "
                f"{', '.join(legal_moves)}\n"
                f"Respond with ONLY the move, nothing else."
            )

        # Exhausted retries — forfeit or random fallback
        import random
        fallback = random.choice(list(board.legal_moves))
        return MoveResult(
            move=fallback,
            tokens_used=total_tokens,
            cost_usd=total_cost,
            think_time_ms=int((time.monotonic() - start_time) * 1000),
            illegal_attempts=illegal_attempts,
            raw_response=f"FALLBACK after {self.max_retries} retries",
        )

    def _call_api(self, system: str, user: str) -> tuple[str, int, float]:
        """Returns (response_text, tokens_used, cost_usd)."""
        if self.provider == "openai":
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            text = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else 0
            cost = self._estimate_cost(resp.usage) if resp.usage else 0.0
            return text, tokens, cost

        elif self.provider == "anthropic":
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=self.temperature,
            )
            text = resp.content[0].text if resp.content else ""
            tokens = (resp.usage.input_tokens + resp.usage.output_tokens)
            cost = self._estimate_cost_anthropic(resp.usage)
            return text, tokens, cost

        elif self.provider == "google":
            resp = self._client.generate_content(
                f"{system}\n\n{user}",
                generation_config={"max_output_tokens": self.max_tokens, "temperature": self.temperature},
            )
            text = resp.text or ""
            tokens = resp.usage_metadata.total_token_count if resp.usage_metadata else 0
            return text, tokens, 0.0  # Google pricing varies

    def _estimate_cost(self, usage) -> float:
        """Rough cost estimation for OpenAI models."""
        # Prices as of early 2026 — update as needed
        pricing = {
            "gpt-4o":       (2.50, 10.00),   # per 1M input, output tokens
            "gpt-4o-mini":  (0.15, 0.60),
            "o4-mini":      (1.10, 4.40),
            "gpt-3.5-turbo-instruct": (1.50, 2.00),
        }
        rates = pricing.get(self.model, (2.50, 10.00))
        input_cost = (usage.prompt_tokens / 1_000_000) * rates[0]
        output_cost = (usage.completion_tokens / 1_000_000) * rates[1]
        return input_cost + output_cost

    def _estimate_cost_anthropic(self, usage) -> float:
        pricing = {
            "claude-sonnet-4-5-20250929": (3.00, 15.00),
            "claude-haiku-4-5-20251001":  (0.80, 4.00),
            "claude-opus-4-6":            (15.00, 75.00),
        }
        rates = pricing.get(self.model, (3.00, 15.00))
        return (usage.input_tokens / 1_000_000) * rates[0] + \
               (usage.output_tokens / 1_000_000) * rates[1]
```

#### UCI Engine Player (Stockfish as a competitor)

```python
# src/players/engine_player.py
import chess.engine
from .base import PlayerAdapter, MoveResult
import time

class UCIEnginePlayer(PlayerAdapter):
    def __init__(self, name: str, engine_path: str,
                 time_limit: float = 0.5, skill_level: int | None = None,
                 elo_limit: int | None = None):
        self.name = name
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.time_limit = time_limit
        if skill_level is not None:
            self.engine.configure({"Skill Level": skill_level})
        if elo_limit is not None:
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo_limit})

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        start = time.monotonic()
        result = self.engine.play(board, chess.engine.Limit(time=self.time_limit))
        elapsed = int((time.monotonic() - start) * 1000)
        return MoveResult(move=result.move, think_time_ms=elapsed)

    def on_game_end(self, result: str) -> None:
        pass  # engine stays alive across games

    def cleanup(self):
        self.engine.quit()
```

### 5.2 Stockfish Analyzer

This runs **after each move** during a live game to provide real-time evaluation, and also runs a deeper post-game analysis.

```python
# src/analysis/analyzer.py
import chess
import chess.engine
from dataclasses import dataclass
import math

@dataclass
class MoveEval:
    eval_before_cp: int | None       # centipawns from white's POV, None = mate
    eval_after_cp: int | None
    mate_before: int | None          # moves to mate (positive = white mates)
    mate_after: int | None
    best_move: chess.Move
    best_move_san: str
    centipawn_loss: int
    classification: str              # "best", "excellent", "good", etc.
    win_pct_before: float            # 0-100 win probability for side to move
    win_pct_after: float

class StockfishAnalyzer:
    def __init__(self, engine_path: str, depth: int = 18, threads: int = 4, hash_mb: int = 256):
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.engine.configure({"Threads": threads, "Hash": hash_mb})
        self.depth = depth

    def analyze_move(self, board_before: chess.Board, move: chess.Move) -> MoveEval:
        """Analyze a single move: evaluate position before and after, find best move."""

        # Eval BEFORE the move (from side-to-move perspective)
        info_before = self.engine.analyse(board_before, chess.engine.Limit(depth=self.depth))
        score_before = info_before["score"].white()

        # Find best move
        best_result = self.engine.play(board_before, chess.engine.Limit(depth=self.depth))
        best_move = best_result.move
        best_san = board_before.san(best_move)

        # Apply the actual move and eval AFTER
        board_after = board_before.copy()
        board_after.push(move)
        info_after = self.engine.analyse(board_after, chess.engine.Limit(depth=self.depth))
        score_after = info_after["score"].white()

        # Convert scores to centipawns
        eval_before_cp = self._score_to_cp(score_before)
        eval_after_cp = self._score_to_cp(score_after)
        mate_before = score_before.mate() if score_before.is_mate() else None
        mate_after = score_after.mate() if score_after.is_mate() else None

        # Calculate centipawn loss
        # CPL = how much the position worsened for the moving side
        if board_before.turn == chess.WHITE:
            cpl = max(0, (eval_before_cp or 0) - (eval_after_cp or 0))
        else:
            cpl = max(0, (eval_after_cp or 0) - (eval_before_cp or 0))

        # If the actual move IS the best move, CPL = 0
        if move == best_move:
            cpl = 0

        classification = self._classify(cpl)

        return MoveEval(
            eval_before_cp=eval_before_cp,
            eval_after_cp=eval_after_cp,
            mate_before=mate_before,
            mate_after=mate_after,
            best_move=best_move,
            best_move_san=best_san,
            centipawn_loss=cpl,
            classification=classification,
            win_pct_before=self._cp_to_win_pct(eval_before_cp),
            win_pct_after=self._cp_to_win_pct(eval_after_cp),
        )

    def _score_to_cp(self, score: chess.engine.PovScore) -> int | None:
        """Convert engine score to centipawns. Mate scores → large values."""
        if score.is_mate():
            mate_in = score.mate()
            return 10000 if mate_in > 0 else -10000
        return score.score()

    def _cp_to_win_pct(self, cp: int | None) -> float:
        """Convert centipawns to win probability (Lichess formula)."""
        if cp is None:
            return 50.0
        return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)

    @staticmethod
    def _classify(cpl: int) -> str:
        if cpl == 0:
            return "best"
        elif cpl <= 10:
            return "excellent"
        elif cpl <= 30:
            return "good"
        elif cpl <= 100:
            return "inaccuracy"
        elif cpl <= 200:
            return "mistake"
        else:
            return "blunder"

    @staticmethod
    def move_accuracy(cpl: int) -> float:
        """Lichess-style per-move accuracy. 100 = perfect, 0 = terrible."""
        return max(0, 103.1668 * math.exp(-0.04354 * min(cpl, 1000)) - 3.1668)

    def shutdown(self):
        self.engine.quit()
```

### 5.3 Game Orchestrator

The core game loop. Plays one complete game, running Stockfish analysis in real time and emitting events for the WebSocket layer.

```python
# src/game/orchestrator.py
import chess
import chess.pgn
import time
import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from ..players.base import PlayerAdapter, MoveResult
from ..analysis.analyzer import StockfishAnalyzer, MoveEval

@dataclass
class LiveMoveEvent:
    """Emitted after each move for WebSocket broadcast."""
    game_id: int
    move_number: int
    color: str
    move_uci: str
    move_san: str
    fen: str
    eval_cp: int | None
    eval_mate: int | None
    best_move_san: str | None
    cpl: int
    classification: str
    win_pct_white: float
    accuracy: float
    think_time_ms: int
    illegal_attempts: int
    white_avg_cpl: float       # running average
    black_avg_cpl: float
    pgn_so_far: str

@dataclass
class GameConfig:
    max_moves: int = 150                # per side (300 half-moves total)
    analyze_depth: int = 18
    move_delay_seconds: float = 1.0     # pause between moves for spectator experience

class GameOrchestrator:
    def __init__(self, analyzer: StockfishAnalyzer, event_callback=None,
                 config: GameConfig | None = None):
        self.analyzer = analyzer
        self.event_callback = event_callback   # async callable for live events
        self.config = config or GameConfig()

    async def play_game(self, game_id: int,
                        white: PlayerAdapter, black: PlayerAdapter) -> dict:
        board = chess.Board()
        game = chess.pgn.Game()
        game.headers["White"] = white.get_name()
        game.headers["Black"] = black.get_name()
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Event"] = "LLM Chess Arena"
        node = game

        white.on_game_start(chess.WHITE)
        black.on_game_start(chess.BLACK)

        move_analyses: list[dict] = []
        white_cpls, black_cpls = [], []
        white_illegals, black_illegals = 0, 0
        white_tokens, black_tokens = 0, 0
        white_cost, black_cost = 0.0, 0.0
        game_history: list[chess.Move] = []

        start_time = time.time()

        while not board.is_game_over(claim_draw=True):
            if board.fullmove_number > self.config.max_moves:
                break

            current = white if board.turn == chess.WHITE else black
            color_str = "white" if board.turn == chess.WHITE else "black"

            # Get move from player
            try:
                result: MoveResult = current.get_move(board, game_history)
            except Exception as e:
                # Player crashed — opponent wins
                winner = "0-1" if board.turn == chess.WHITE else "1-0"
                game.headers["Result"] = winner
                return self._build_game_data(
                    game_id, game, board, winner, f"error:{e}",
                    move_analyses, white_cpls, black_cpls,
                    white_illegals, black_illegals,
                    white_tokens, black_tokens, white_cost, black_cost,
                    start_time, white, black,
                )

            # Track stats
            if board.turn == chess.WHITE:
                white_illegals += result.illegal_attempts
                white_tokens += result.tokens_used
                white_cost += result.cost_usd
            else:
                black_illegals += result.illegal_attempts
                black_tokens += result.tokens_used
                black_cost += result.cost_usd

            # Stockfish analysis BEFORE pushing the move
            move_eval: MoveEval = self.analyzer.analyze_move(board, result.move)

            # Track CPL
            if board.turn == chess.WHITE:
                white_cpls.append(move_eval.centipawn_loss)
            else:
                black_cpls.append(move_eval.centipawn_loss)

            # Record move
            san = board.san(result.move)
            fen_before = board.fen()
            board.push(result.move)
            fen_after = board.fen()
            node = node.add_variation(result.move)
            game_history.append(result.move)

            analysis_record = {
                "game_id": game_id,
                "move_number": board.fullmove_number - (1 if board.turn == chess.WHITE else 0),
                "color": color_str,
                "move_uci": result.move.uci(),
                "move_san": san,
                "fen_before": fen_before,
                "fen_after": fen_after,
                "eval_before_cp": move_eval.eval_before_cp,
                "eval_after_cp": move_eval.eval_after_cp,
                "best_move_uci": move_eval.best_move.uci(),
                "best_move_san": move_eval.best_move_san,
                "centipawn_loss": move_eval.centipawn_loss,
                "classification": move_eval.classification,
                "think_time_ms": result.think_time_ms,
                "tokens_used": result.tokens_used,
                "illegal_attempts": result.illegal_attempts,
            }
            move_analyses.append(analysis_record)

            # Emit live event for WebSocket
            if self.event_callback:
                event = LiveMoveEvent(
                    game_id=game_id,
                    move_number=len(game_history),
                    color=color_str,
                    move_uci=result.move.uci(),
                    move_san=san,
                    fen=fen_after,
                    eval_cp=move_eval.eval_after_cp,
                    eval_mate=move_eval.mate_after,
                    best_move_san=move_eval.best_move_san,
                    cpl=move_eval.centipawn_loss,
                    classification=move_eval.classification,
                    win_pct_white=move_eval.win_pct_after if board.turn == chess.BLACK
                                  else 100 - move_eval.win_pct_after,
                    accuracy=self.analyzer.move_accuracy(move_eval.centipawn_loss),
                    think_time_ms=result.think_time_ms,
                    illegal_attempts=result.illegal_attempts,
                    white_avg_cpl=sum(white_cpls) / max(len(white_cpls), 1),
                    black_avg_cpl=sum(black_cpls) / max(len(black_cpls), 1),
                    pgn_so_far=str(game),
                )
                await self.event_callback(event)

            # Pace for spectators
            await asyncio.sleep(self.config.move_delay_seconds)

        # Determine result
        outcome = board.outcome(claim_draw=True)
        if outcome:
            result_str = outcome.result()
            termination = outcome.termination.name.lower()
        else:
            result_str = "1/2-1/2"
            termination = "max_moves"

        game.headers["Result"] = result_str

        white.on_game_end(result_str)
        black.on_game_end(result_str)

        return self._build_game_data(
            game_id, game, board, result_str, termination,
            move_analyses, white_cpls, black_cpls,
            white_illegals, black_illegals,
            white_tokens, black_tokens, white_cost, black_cost,
            start_time, white, black,
        )

    def _build_game_data(self, game_id, game, board, result, termination,
                         analyses, w_cpls, b_cpls, w_illegals, b_illegals,
                         w_tokens, b_tokens, w_cost, b_cost, start_time,
                         white, black) -> dict:
        import math

        def avg(lst): return sum(lst) / max(len(lst), 1)
        def game_accuracy(cpls):
            return avg([self.analyzer.move_accuracy(c) for c in cpls]) if cpls else 0

        return {
            "game_id": game_id,
            "white": white.get_name(),
            "black": black.get_name(),
            "result": result,
            "termination": termination,
            "pgn": str(game),
            "moves_count": len(analyses),
            "white_avg_cpl": round(avg(w_cpls), 1),
            "black_avg_cpl": round(avg(b_cpls), 1),
            "white_accuracy": round(game_accuracy(w_cpls), 1),
            "black_accuracy": round(game_accuracy(b_cpls), 1),
            "white_blunders": sum(1 for c in w_cpls if c > 200),
            "black_blunders": sum(1 for c in b_cpls if c > 200),
            "white_mistakes": sum(1 for c in w_cpls if 100 < c <= 200),
            "black_mistakes": sum(1 for c in b_cpls if 100 < c <= 200),
            "white_illegal_attempts": w_illegals,
            "black_illegal_attempts": b_illegals,
            "white_tokens": w_tokens,
            "black_tokens": b_tokens,
            "white_cost_usd": round(w_cost, 4),
            "black_cost_usd": round(b_cost, 4),
            "duration_seconds": round(time.time() - start_time, 1),
            "move_analyses": analyses,
        }
```

### 5.4 Tournament Manager

```python
# src/game/tournament.py
import itertools
import math
from ..players.base import PlayerAdapter

class EloCalculator:
    """Standard Elo rating system."""
    K = 32  # K-factor

    @staticmethod
    def expected_score(rating_a: float, rating_b: float) -> float:
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    @staticmethod
    def update(rating: float, expected: float, actual: float) -> float:
        return rating + EloCalculator.K * (actual - expected)

class TournamentManager:
    def __init__(self, players: list[PlayerAdapter], orchestrator, db_session,
                 rounds: int = 1):
        self.players = players
        self.orchestrator = orchestrator
        self.db = db_session
        self.rounds = rounds
        self.elo_ratings: dict[str, float] = {p.get_name(): 1200.0 for p in players}

    async def run_round_robin(self, event_callback=None):
        """Every player plays every other with both colors, `rounds` times."""
        pairings = list(itertools.combinations(range(len(self.players)), 2))
        game_id = 0

        for round_num in range(self.rounds):
            for i, j in pairings:
                for w_idx, b_idx in [(i, j), (j, i)]:
                    game_id += 1
                    white = self.players[w_idx]
                    black = self.players[b_idx]

                    # Notify spectators: new game starting
                    if event_callback:
                        await event_callback({
                            "type": "game_start",
                            "game_id": game_id,
                            "white": white.get_name(),
                            "black": black.get_name(),
                            "round": round_num + 1,
                        })

                    result = await self.orchestrator.play_game(game_id, white, black)

                    # Update Elo
                    self._update_elo(white.get_name(), black.get_name(), result["result"])

                    # Persist to database
                    self._save_game(result)

                    # Broadcast game complete
                    if event_callback:
                        await event_callback({
                            "type": "game_end",
                            "game_id": game_id,
                            "result": result["result"],
                            "standings": self.get_standings(),
                        })

    def _update_elo(self, white_name: str, black_name: str, result: str):
        w_elo = self.elo_ratings[white_name]
        b_elo = self.elo_ratings[black_name]

        expected_w = EloCalculator.expected_score(w_elo, b_elo)
        expected_b = 1 - expected_w

        if result == "1-0":
            actual_w, actual_b = 1.0, 0.0
        elif result == "0-1":
            actual_w, actual_b = 0.0, 1.0
        else:
            actual_w, actual_b = 0.5, 0.5

        self.elo_ratings[white_name] = EloCalculator.update(w_elo, expected_w, actual_w)
        self.elo_ratings[black_name] = EloCalculator.update(b_elo, expected_b, actual_b)

    def get_standings(self) -> list[dict]:
        # Aggregate from DB — simplified here
        standings = []
        for name, elo in sorted(self.elo_ratings.items(), key=lambda x: -x[1]):
            standings.append({"name": name, "elo": round(elo, 1)})
        return standings

    def _save_game(self, result: dict):
        """Persist game + move analyses to database."""
        # Insert into Game and MoveAnalysis tables via SQLModel
        pass
```

### 5.5 API Server

```python
# src/api/server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI(title="LLM Chess Arena")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, message: dict):
        data = json.dumps(message, default=str)
        for ws in self.active:
            try:
                await ws.send_text(data)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/live")
async def live_game_ws(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        manager.disconnect(ws)

# REST endpoints
@app.get("/api/standings")
async def get_standings():
    """Current tournament standings with Elo, W/L/D, accuracy stats."""
    pass  # Query DB

@app.get("/api/games")
async def list_games(limit: int = 20, offset: int = 0):
    """Paginated list of completed games."""
    pass

@app.get("/api/games/{game_id}")
async def get_game(game_id: int):
    """Full game detail with PGN and per-move analysis."""
    pass

@app.get("/api/games/{game_id}/analysis")
async def get_game_analysis(game_id: int):
    """Per-move Stockfish analysis for a specific game."""
    pass

@app.get("/api/players/{player_name}/stats")
async def get_player_stats(player_name: str):
    """Detailed stats for a specific player/model."""
    pass

@app.get("/api/live")
async def get_live_state():
    """Current game state for late-joining spectators."""
    pass
```

### 5.6 Frontend Pages

**Page 1: Live Game (`/`)**

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM CHESS ARENA         [Live] ● Game #47                      │
├─────────────────────┬───────────────────────────────────────────┤
│                     │  ♚ Claude Sonnet 4.5 (Black)              │
│                     │  Elo: 1087  │  Accuracy: 62.3%            │
│                     │  Think time: 2.3s avg                     │
│     ┌───────────┐   ├───────────────────────────────────────────┤
│     │           │   │                                           │
│     │  CHESS    │   │  Eval: +1.7  ████████░░  63% White       │
│     │  BOARD    │   │                                           │
│     │  (react-  │   │  Move 23: Nf3  (Good, CPL: 18)           │
│     │  chess-   │   │  Best was: Nd5  (+2.1)                    │
│     │  board)   │   │                                           │
│     │           │   │  ┌─── Eval Over Time ──────────────┐     │
│     └───────────┘   │  │  📈 Sparkline chart of eval     │     │
│                     │  │     per move (white POV)         │     │
│  ♔ GPT-4o (White)   │  └────────────────────────────────────┘   │
│  Elo: 1143          ├───────────────────────────────────────────┤
│  Accuracy: 71.8%    │  Move List (PGN)                          │
│                     │  1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 ...       │
│                     │                                           │
├─────────────────────┴───────────────────────────────────────────┤
│                     SCOREBOARD                                   │
│  ┌──────────────────┬──────┬─────┬───────┬──────┬──────────────┐│
│  │ Model            │ Elo  │ W/L/D│ Acc% │ CPL  │ Blunders/g  ││
│  ├──────────────────┼──────┼─────┼───────┼──────┼──────────────┤│
│  │ o4-mini          │ 1384 │ 8/1/1│ 78.2 │ 34.1 │ 0.8         ││
│  │ GPT-4o           │ 1243 │ 6/3/1│ 71.8 │ 48.3 │ 1.2         ││
│  │ Grok-3-mini      │ 1187 │ 5/4/1│ 65.1 │ 56.7 │ 2.1         ││
│  │ Claude Sonnet    │ 1087 │ 3/6/1│ 62.3 │ 63.4 │ 2.8         ││
│  │ Gemini 2.5 Pro   │ 1034 │ 2/7/1│ 58.9 │ 71.2 │ 3.4         ││
│  └──────────────────┴──────┴─────┴───────┴──────┴──────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Page 2: Game Archive (`/games/:id`)**

Full post-game analysis view:
- Interactive board with move-by-move navigation
- Per-move accuracy chart (bar chart colored by classification)
- Eval graph (line chart over moves)
- Move table with CPL, classification, best move alternative
- Head-to-head stats between the two players
- PGN download button

**Page 3: Player Profile (`/players/:name`)**

- Elo history chart over time
- Accuracy distribution histogram
- Opening repertoire stats
- Win rate by color (white vs black)
- Avg tokens per move / cost per game
- Illegal move rate over time
- Head-to-head records vs each opponent

---

## 6. Key Metrics Tracked

| Metric | Granularity | Description |
|--------|-------------|-------------|
| **Elo Rating** | Per player | Standard Elo, K=32, starting at 1200 |
| **Avg Centipawn Loss (CPL)** | Per game, per player, career | Lower = better. Elite humans: 20-30 |
| **Accuracy %** | Per move, per game, career | Lichess-style formula. Humans ~70-85% |
| **Blunder Rate** | Per game | Moves with CPL > 200 per game |
| **Mistake Rate** | Per game | Moves with CPL > 100 per game |
| **Illegal Move Rate** | Per game, career | Retries needed before legal move. Unique to LLMs |
| **Best Move %** | Per game, career | % of moves matching Stockfish's top choice |
| **Win/Loss/Draw** | Per player | Overall and per-opponent |
| **Avg Think Time** | Per move, per game | LLM API latency per move |
| **Token Usage** | Per move, per game, career | Total tokens consumed |
| **Cost per Game** | Per game, career | USD spent on API calls |
| **Opening Repertoire** | Per player | Which openings the LLM gravitates toward |
| **Endgame Accuracy** | Per game | Accuracy in last 20 moves vs first 20 |
| **Material Advantage Conversion** | Career | Win rate when up material |
| **Game Length** | Per game | Avg moves per game (proxy for instruction-following durability) |

---

## 7. Project Structure

```
llm-chess-arena/
├── README.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example                   # API keys template
│
├── backend/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                # Entry point: starts tournament + API server
│   │   ├── config.py              # Pydantic Settings (env vars, API keys)
│   │   ├── players/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # PlayerAdapter ABC, MoveResult
│   │   │   ├── llm_player.py      # LLM adapter (OpenAI, Anthropic, Google)
│   │   │   ├── engine_player.py   # UCI engine adapter (Stockfish, Lc0)
│   │   │   └── pgn_player.py      # PGN-completion style (gpt-3.5-turbo-instruct)
│   │   ├── analysis/
│   │   │   ├── __init__.py
│   │   │   ├── analyzer.py        # StockfishAnalyzer (per-move eval + classification)
│   │   │   └── accuracy.py        # Lichess-style accuracy formulas
│   │   ├── game/
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py    # GameOrchestrator (core game loop)
│   │   │   ├── tournament.py      # TournamentManager + EloCalculator
│   │   │   └── openings.py        # ECO opening book lookup
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── server.py          # FastAPI app, WebSocket, REST routes
│   │   │   ├── models.py          # Pydantic response models
│   │   │   └── dependencies.py    # DB session, shared state
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── models.py          # SQLModel table definitions
│   │       ├── session.py         # Engine + session factory
│   │       └── migrations/        # Alembic migrations (if Postgres)
│   │
│   ├── tests/
│   │   ├── test_analyzer.py
│   │   ├── test_orchestrator.py
│   │   ├── test_llm_player.py
│   │   └── test_elo.py
│   │
│   └── games/                     # PGN file archive
│
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Live game view
│   │   │   ├── games/
│   │   │   │   ├── page.tsx       # Game archive list
│   │   │   │   └── [id]/page.tsx  # Single game analysis
│   │   │   └── players/
│   │   │       └── [name]/page.tsx # Player profile
│   │   ├── components/
│   │   │   ├── LiveBoard.tsx      # react-chessboard + WebSocket
│   │   │   ├── EvalBar.tsx        # Vertical evaluation bar
│   │   │   ├── EvalChart.tsx      # Eval over time sparkline
│   │   │   ├── MoveList.tsx       # Annotated PGN move list
│   │   │   ├── Scoreboard.tsx     # Tournament standings table
│   │   │   ├── AccuracyChart.tsx  # Per-move accuracy bars
│   │   │   ├── PlayerCard.tsx     # Player stats card
│   │   │   └── GameCard.tsx       # Game summary card
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts    # WebSocket connection hook
│   │   │   └── useGameState.ts    # Derived game state from WS events
│   │   └── lib/
│   │       ├── api.ts             # REST API client
│   │       └── types.ts           # Shared TypeScript types
│   │
│   └── public/
│       └── pieces/                # Optional custom piece SVGs
│
└── scripts/
    ├── setup.sh                   # Install deps, download Stockfish
    ├── seed_players.py            # Initialize player configs
    └── run_tournament.py          # CLI to start a tournament
```

---

## 8. WebSocket Event Protocol

All events are JSON over a single WebSocket connection at `/ws/live`.

```typescript
// Server → Client events

interface GameStartEvent {
  type: "game_start";
  game_id: number;
  white: string;          // player name
  black: string;
  round: number;
}

interface MoveEvent {
  type: "move";
  game_id: number;
  move_number: number;
  color: "white" | "black";
  move_uci: string;       // "e2e4"
  move_san: string;       // "e4"
  fen: string;            // position after move
  eval_cp: number | null; // centipawns from white POV
  eval_mate: number | null;
  best_move_san: string;
  cpl: number;            // centipawn loss for this move
  classification: "best" | "excellent" | "good" | "inaccuracy" | "mistake" | "blunder";
  win_pct_white: number;  // 0-100
  accuracy: number;       // 0-100 for this move
  think_time_ms: number;
  illegal_attempts: number;
  white_avg_cpl: number;  // running game averages
  black_avg_cpl: number;
}

interface GameEndEvent {
  type: "game_end";
  game_id: number;
  result: "1-0" | "0-1" | "1/2-1/2";
  termination: string;
  white_accuracy: number;
  black_accuracy: number;
  standings: StandingsEntry[];
}

interface StandingsEntry {
  name: string;
  elo: number;
  wins: number;
  losses: number;
  draws: number;
  avg_accuracy: number;
  avg_cpl: number;
  blunder_rate: number;
  total_cost_usd: number;
}
```

---

## 9. Configuration

```yaml
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
STOCKFISH_PATH=/usr/local/bin/stockfish
DATABASE_URL=sqlite:///./arena.db
ANALYSIS_DEPTH=18
STOCKFISH_THREADS=4
STOCKFISH_HASH_MB=256
MOVE_DELAY_SECONDS=1.5
MAX_MOVES_PER_SIDE=150
LLM_MAX_RETRIES=5
LLM_TEMPERATURE=0.0
```

```python
# backend/src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Stockfish
    stockfish_path: str = "/usr/local/bin/stockfish"
    analysis_depth: int = 18
    stockfish_threads: int = 4
    stockfish_hash_mb: int = 256

    # Game settings
    move_delay_seconds: float = 1.5
    max_moves_per_side: int = 150
    llm_max_retries: int = 5
    llm_temperature: float = 0.0

    # Database
    database_url: str = "sqlite:///./arena.db"

    # Players to include in tournament
    players: list[dict] = [
        {"name": "GPT-4o", "provider": "openai", "model": "gpt-4o"},
        {"name": "o4-mini", "provider": "openai", "model": "o4-mini"},
        {"name": "Claude Sonnet", "provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        {"name": "Gemini 2.5 Pro", "provider": "google", "model": "gemini-2.5-pro"},
        {"name": "Stockfish-800", "provider": "engine", "model": "stockfish", "elo_limit": 800},
    ]

    class Config:
        env_file = ".env"
```

---

## 10. Development Phases

### Phase 1: Core Engine (Week 1)
- `PlayerAdapter` base + `UCIEnginePlayer` (Stockfish vs Stockfish)
- `StockfishAnalyzer` with CPL and classification
- `GameOrchestrator` producing complete game data with analysis
- Unit tests for all analysis math
- PGN output validation

### Phase 2: LLM Integration (Week 2)
- `LLMPlayer` with OpenAI, Anthropic, Google providers
- Illegal move retry logic with SAN/UCI fallback parsing
- Token tracking and cost estimation
- Test: GPT-4o vs Claude Sonnet (just console output)

### Phase 3: API + Real-Time (Week 3)
- FastAPI server with WebSocket broadcasting
- REST endpoints for standings, games, analysis
- `TournamentManager` with round-robin scheduling
- Elo rating system
- SQLite persistence

### Phase 4: Frontend (Week 4)
- Next.js app with `react-chessboard` live board
- WebSocket hook for real-time move updates
- Eval bar + eval chart components
- Scoreboard table with sorting
- Move list with color-coded classifications

### Phase 5: Polish (Week 5)
- Game archive with full post-game analysis view
- Player profile pages with stat breakdowns
- Accuracy distribution histograms
- Opening book detection (ECO codes)
- Docker Compose for one-command deployment
- README with setup instructions

---

## 11. Cost Projections

For a round-robin tournament with 5 LLMs, both colors, 2 rounds:

- Pairings: C(5,2) = 10 matchups × 2 colors × 2 rounds = **40 games**
- Avg game length: ~45 moves = 90 half-moves
- Tokens per move request: ~200 input + ~10 output ≈ 210 tokens

| Model | $/1M input | $/1M output | Est. cost/game | 40 games |
|-------|-----------|------------|----------------|----------|
| gpt-4o | $2.50 | $10.00 | ~$0.05 | ~$2.00 |
| o4-mini | $1.10 | $4.40 | ~$0.03 | ~$1.20 |
| Claude Sonnet 4.5 | $3.00 | $15.00 | ~$0.06 | ~$2.40 |
| Claude Haiku 4.5 | $0.80 | $4.00 | ~$0.02 | ~$0.80 |
| Gemini 2.5 Pro | $1.25 | $10.00 | ~$0.04 | ~$1.60 |

**Total estimated cost for a 40-game tournament: ~$8–15**

Adding retries for illegal moves increases cost ~20-50% for weaker chess models (Claude, Gemini).

---

## 12. Deployment

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data          # SQLite + PGN storage
      - stockfish:/usr/local/bin   # Stockfish binary
    command: uvicorn src.api.server:app --host 0.0.0.0 --port 8000

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      - NEXT_PUBLIC_WS_URL=ws://backend:8000/ws/live

  # Optional: for production scaling
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

For a quick single-machine dev setup, just run the backend and frontend directly:

```bash
# Terminal 1: Backend
cd backend && uvicorn src.api.server:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Start tournament
cd backend && python -m scripts.run_tournament
```

---

## 13. Key References

| Resource | URL | Relevance |
|----------|-----|-----------|
| python-chess docs | python-chess.readthedocs.io | Board state, UCI engine comms, PGN |
| python-chess engine module | python-chess.readthedocs.io/en/latest/engine.html | `SimpleEngine.popen_uci()`, `engine.play()`, `engine.analyse()` |
| react-chessboard | github.com/Clariity/react-chessboard | Frontend board component (18K weekly downloads) |
| chess.js | github.com/jhlywa/chess.js | Client-side move validation |
| maxim-saplin/llm_chess | github.com/maxim-saplin/llm_chess | LLM chess benchmark, Elo methodology, NeurIPS paper |
| LLM Chess Leaderboard | maxim-saplin.github.io/llm_chess | Current LLM Elo ratings and capabilities |
| carlini/chess-llm | github.com/carlini/chess-llm | UCI wrapper for GPT, PGN-completion approach |
| Lichess accuracy formula | lichess.org/page/accuracy | CPL → accuracy % conversion |
| chessground | github.com/lichess-org/chessground | Alternative board UI (GPL, used by Lichess) |
| Stockfish | stockfishchess.org | Analysis engine binary |