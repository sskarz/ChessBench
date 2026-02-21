"use client";

import { useReducer, useEffect, useCallback } from "react";
import { useWebSocket, type ConnectionStatus } from "./useWebSocket";
import { getLiveState, getStandings } from "@/lib/api";
import type {
  WSEvent,
  MoveEvent,
  StandingsEntry,
} from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/live";
const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export type TournamentStatus =
  | "idle"
  | "running"
  | "completed"
  | "error"
  | "queued";

export interface SingleGameState {
  gameId: number;
  white: string;
  black: string;
  round: number;
  fen: string;
  moves: MoveEvent[];
  isActive: boolean;
  result: string | null;
}

interface MultiGameState {
  games: Record<number, SingleGameState>;
  selectedGameId: number | null;
  standings: StandingsEntry[];
  tournamentStatus: TournamentStatus;
  error: string | null;
}

type Action =
  | { type: "GAME_START"; payload: { gameId: number; white: string; black: string; round: number } }
  | { type: "MOVE"; payload: MoveEvent }
  | { type: "GAME_END"; payload: { gameId: number; result: string; standings: StandingsEntry[] } }
  | { type: "TOURNAMENT_COMPLETE"; payload: { standings: StandingsEntry[] } }
  | { type: "TOURNAMENT_ERROR"; payload: { error: string } }
  | { type: "TOURNAMENT_QUEUED" }
  | { type: "SELECT_GAME"; payload: { gameId: number } }
  | { type: "HYDRATE"; payload: Partial<MultiGameState> }
  | { type: "SET_STANDINGS"; payload: StandingsEntry[] };

const initialState: MultiGameState = {
  games: {},
  selectedGameId: null,
  standings: [],
  tournamentStatus: "idle",
  error: null,
};

function reducer(state: MultiGameState, action: Action): MultiGameState {
  switch (action.type) {
    case "GAME_START": {
      const { gameId, white, black, round } = action.payload;
      const newGame: SingleGameState = {
        gameId,
        white,
        black,
        round,
        fen: STARTING_FEN,
        moves: [],
        isActive: true,
        result: null,
      };
      const games = { ...state.games, [gameId]: newGame };
      // Auto-select if nothing selected
      const selectedGameId = state.selectedGameId ?? gameId;
      return {
        ...state,
        games,
        selectedGameId,
        tournamentStatus: "running",
        error: null,
      };
    }
    case "MOVE": {
      const gameId = action.payload.game_id;
      const existing = state.games[gameId];
      if (!existing) return state;
      return {
        ...state,
        games: {
          ...state.games,
          [gameId]: {
            ...existing,
            fen: action.payload.fen,
            moves: [...existing.moves, action.payload],
          },
        },
      };
    }
    case "GAME_END": {
      const { gameId, result, standings } = action.payload;
      const existing = state.games[gameId];
      if (!existing) return { ...state, standings };
      const updatedGames = {
        ...state.games,
        [gameId]: { ...existing, isActive: false, result },
      };
      // If selected game just ended and other games are active, auto-select another
      let selectedGameId = state.selectedGameId;
      if (selectedGameId === gameId) {
        const activeGame = Object.values(updatedGames).find((g) => g.isActive);
        selectedGameId = activeGame?.gameId ?? selectedGameId;
      }
      return {
        ...state,
        games: updatedGames,
        selectedGameId,
        standings,
      };
    }
    case "TOURNAMENT_COMPLETE":
      return {
        ...state,
        games: {},
        selectedGameId: null,
        tournamentStatus: "completed",
        standings: action.payload.standings,
      };
    case "TOURNAMENT_ERROR":
      return {
        ...state,
        tournamentStatus: "error",
        error: action.payload.error,
      };
    case "TOURNAMENT_QUEUED":
      return {
        ...state,
        tournamentStatus: "queued",
      };
    case "SELECT_GAME":
      return {
        ...state,
        selectedGameId: action.payload.gameId,
      };
    case "HYDRATE":
      return { ...state, ...action.payload };
    case "SET_STANDINGS":
      return { ...state, standings: action.payload };
    default:
      return state;
  }
}

export interface UseGameStateReturn {
  games: Record<number, SingleGameState>;
  selectedGameId: number | null;
  selectedGame: SingleGameState | null;
  standings: StandingsEntry[];
  tournamentStatus: TournamentStatus;
  error: string | null;
  wsStatus: ConnectionStatus;
  selectGame: (gameId: number) => void;
}

export function useGameState(): UseGameStateReturn {
  const [state, dispatch] = useReducer(reducer, initialState);

  const handleMessage = useCallback((event: WSEvent) => {
    switch (event.type) {
      case "game_start":
        dispatch({
          type: "GAME_START",
          payload: {
            gameId: event.game_id,
            white: event.white,
            black: event.black,
            round: event.round,
          },
        });
        break;
      case "move":
        dispatch({ type: "MOVE", payload: event });
        break;
      case "game_end":
        dispatch({
          type: "GAME_END",
          payload: {
            gameId: event.game_id,
            result: event.result,
            standings: event.standings,
          },
        });
        break;
      case "tournament_complete":
        dispatch({
          type: "TOURNAMENT_COMPLETE",
          payload: { standings: event.standings },
        });
        break;
      case "tournament_error":
        dispatch({
          type: "TOURNAMENT_ERROR",
          payload: { error: event.error },
        });
        break;
      case "tournament_queued":
        dispatch({ type: "TOURNAMENT_QUEUED" });
        break;
    }
  }, []);

  const { status: wsStatus } = useWebSocket({
    url: WS_URL,
    onMessage: handleMessage,
  });

  const selectGame = useCallback((gameId: number) => {
    dispatch({ type: "SELECT_GAME", payload: { gameId } });
  }, []);

  // Hydrate on mount for late-join
  useEffect(() => {
    async function hydrate() {
      try {
        const [live, standings] = await Promise.all([
          getLiveState().catch(() => null),
          getStandings().catch(() => []),
        ]);

        if (standings.length > 0) {
          dispatch({ type: "SET_STANDINGS", payload: standings });
        }

        if (live && live.status === "running") {
          // Hydrate active games
          if (live.active_games && live.active_games.length > 0) {
            for (const game of live.active_games) {
              dispatch({
                type: "GAME_START",
                payload: {
                  gameId: game.game_id,
                  white: game.white,
                  black: game.black,
                  round: game.round,
                },
              });
            }
            // Hydrate last move events for FEN
            if (live.last_events) {
              for (const [, event] of Object.entries(live.last_events)) {
                if (event && event.type === "move") {
                  dispatch({ type: "MOVE", payload: event as unknown as MoveEvent });
                }
              }
            }
          } else if (live.current_game) {
            // Backward compat: single-game hydration
            dispatch({
              type: "GAME_START",
              payload: {
                gameId: live.current_game.game_id,
                white: live.current_game.white,
                black: live.current_game.black,
                round: live.current_game.round,
              },
            });
            if (live.last_event && live.last_event.type === "move") {
              dispatch({ type: "MOVE", payload: live.last_event as unknown as MoveEvent });
            }
          }
          dispatch({
            type: "HYDRATE",
            payload: {
              tournamentStatus: "running",
              standings: live.latest_standings,
            },
          });
        } else if (live && live.status === "completed") {
          dispatch({
            type: "HYDRATE",
            payload: {
              tournamentStatus: "completed",
              standings: live.latest_standings,
            },
          });
        } else if (live && live.status === "error") {
          dispatch({
            type: "HYDRATE",
            payload: {
              tournamentStatus: "error",
              error: live.error,
            },
          });
        }
      } catch {
        // Backend not available — will populate when WS connects
      }
    }

    hydrate();
  }, []);

  const selectedGame = state.selectedGameId != null ? (state.games[state.selectedGameId] ?? null) : null;

  return {
    games: state.games,
    selectedGameId: state.selectedGameId,
    selectedGame,
    standings: state.standings,
    tournamentStatus: state.tournamentStatus,
    error: state.error,
    wsStatus,
    selectGame,
  };
}
