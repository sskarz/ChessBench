# ChessBench — LLM Chess Arena

## Project Overview

ChessBench is an LLM Chess Arena — a platform where LLMs (like Claude, GPT-5.2, Gemini) play chess against each other and against Stockfish. Games are analyzed move-by-move by Stockfish in real-time, providing Elo ratings, accuracy metrics, and live spectating via WebSocket. It uses OpenRouter as a unified API gateway for LLMs.

### Tech Stack

*   **Backend:** Python 3.11+, FastAPI, SQLModel (SQLite default), Stockfish, OpenRouter (for LLM access), `uv` for dependency management.
*   **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, `react-chessboard`, `recharts`, `motion`.
*   **Infrastructure:** Docker, Docker Compose.

## Architecture

*   **Frontend:** Provides a live spectating interface with an interactive board, evaluation bars, move lists, and tournament scoreboards. It communicates with the backend via REST API and WebSocket for real-time updates.
*   **Backend:** Consists of a FastAPI server handling REST endpoints and WebSocket connections. It includes a `GameOrchestrator` for the core game loop, `StockfishAnalyzer` for real-time move evaluation, and `TournamentManager` for scheduling and Elo updates.
*   **Player Adapters:** Interfaces for different players (`LLMPlayer` via OpenRouter and `UCIEnginePlayer` for Stockfish).
*   **Data Layer:** SQLite database (managed via SQLModel) storing players, games, per-move analysis, and tournaments.

## Building and Running

### Quick Start (Docker)

1.  Copy `.env.example` to `.env` and add your `OPENROUTER_API_KEY`.
2.  Run `docker compose up --build`.
3.  Frontend: `http://localhost:3000`
4.  Backend API: `http://localhost:8000`

### Backend Development

1.  Navigate to the `backend` directory: `cd backend`
2.  Copy `.env.example` to `.env` and configure your API keys. Ensure Stockfish is installed and accessible.
3.  Install dependencies using `uv`: `uv sync`
4.  Run tests: `uv run pytest -q`
5.  Run linting: `uv run ruff check .`
6.  Start development server: `uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000`

### Frontend Development

1.  Navigate to the `frontend` directory: `cd frontend`
2.  Install dependencies: `npm install`
3.  Start development server: `npm run dev` (starts on port 3000)
4.  Type-check and build: `npm run build`

## Development Conventions

### Backend

*   **Language:** Python 3.11+
*   **Style:** PEP 8, 4-space indentation, explicit type hints. Use `snake_case` for modules/functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
*   **API:** Define response schemas in `api/models.py`. Do not use ad-hoc response dictionaries in route handlers.
*   **Testing:** Use `pytest` and `pytest-asyncio`. Test names should describe behavior (e.g., `test_start_tournament_rejects_when_running`).
*   **LLM Integration:** All LLM calls should go through the OpenRouter API.

### Frontend

*   **Framework:** Next.js App Router.
*   **Components:** All pages and components are Client Components (`"use client"`).
*   **Libraries:** Use `motion/react` (not `framer-motion`) for animations. Use `react-chessboard` (v5) for the board UI.
*   **Styling:** Tailwind CSS 4. Classification colors use CSS custom properties defined in `globals.css`.
*   **Linting/Typing:** No ESLint is configured. Rely on TypeScript compiler errors during `npm run build` for type checking. Ensure frontend types in `lib/types.ts` remain synchronized with backend Pydantic models.