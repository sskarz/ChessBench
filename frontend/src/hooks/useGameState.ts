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

interface GameState {
  gameId: number | null;
  white: string | null;
  black: string | null;
  round: number | null;
  fen: string;
  moves: MoveEvent[];
  isGameActive: boolean;
  result: string | null;
  standings: StandingsEntry[];
  tournamentStatus: TournamentStatus;
  error: string | null;
}

type Action =
  | { type: "GAME_START"; payload: { gameId: number; white: string; black: string; round: number } }
  | { type: "MOVE"; payload: MoveEvent }
  | { type: "GAME_END"; payload: { result: string; standings: StandingsEntry[] } }
  | { type: "TOURNAMENT_COMPLETE"; payload: { standings: StandingsEntry[] } }
  | { type: "TOURNAMENT_ERROR"; payload: { error: string } }
  | { type: "TOURNAMENT_QUEUED" }
  | { type: "HYDRATE"; payload: Partial<GameState> }
  | { type: "SET_STANDINGS"; payload: StandingsEntry[] };

const initialState: GameState = {
  gameId: null,
  white: null,
  black: null,
  round: null,
  fen: STARTING_FEN,
  moves: [],
  isGameActive: false,
  result: null,
  standings: [],
  tournamentStatus: "idle",
  error: null,
};

function reducer(state: GameState, action: Action): GameState {
  switch (action.type) {
    case "GAME_START":
      return {
        ...state,
        gameId: action.payload.gameId,
        white: action.payload.white,
        black: action.payload.black,
        round: action.payload.round,
        fen: STARTING_FEN,
        moves: [],
        isGameActive: true,
        result: null,
        tournamentStatus: "running",
        error: null,
      };
    case "MOVE":
      return {
        ...state,
        fen: action.payload.fen,
        moves: [...state.moves, action.payload],
      };
    case "GAME_END":
      return {
        ...state,
        isGameActive: false,
        result: action.payload.result,
        standings: action.payload.standings,
      };
    case "TOURNAMENT_COMPLETE":
      return {
        ...state,
        isGameActive: false,
        tournamentStatus: "completed",
        standings: action.payload.standings,
      };
    case "TOURNAMENT_ERROR":
      return {
        ...state,
        isGameActive: false,
        tournamentStatus: "error",
        error: action.payload.error,
      };
    case "TOURNAMENT_QUEUED":
      return {
        ...state,
        tournamentStatus: "queued",
      };
    case "HYDRATE":
      return { ...state, ...action.payload };
    case "SET_STANDINGS":
      return { ...state, standings: action.payload };
    default:
      return state;
  }
}

export interface UseGameStateReturn extends GameState {
  wsStatus: ConnectionStatus;
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
          payload: { result: event.result, standings: event.standings },
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

        if (live && live.status === "running" && live.current_game) {
          dispatch({
            type: "HYDRATE",
            payload: {
              gameId: live.current_game.game_id,
              white: live.current_game.white,
              black: live.current_game.black,
              round: live.current_game.round,
              isGameActive: true,
              tournamentStatus: "running",
              standings: live.latest_standings,
            },
          });

          // Hydrate last event if it was a move
          if (live.last_event && live.last_event.type === "move") {
            const moveEvt = live.last_event as unknown as MoveEvent;
            dispatch({
              type: "HYDRATE",
              payload: { fen: moveEvt.fen },
            });
          }
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

  return { ...state, wsStatus };
}
