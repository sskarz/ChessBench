import type {
  StandingsEntry,
  GameListResponse,
  GameDetail,
  GameAnalysisResponse,
  PlayerStats,
  LiveStateResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function getStandings(): Promise<StandingsEntry[]> {
  return fetchJSON<StandingsEntry[]>("/api/standings");
}

export function getGames(
  limit: number = 20,
  offset: number = 0
): Promise<GameListResponse> {
  return fetchJSON<GameListResponse>(
    `/api/games?limit=${limit}&offset=${offset}`
  );
}

export function getGame(id: number): Promise<GameDetail> {
  return fetchJSON<GameDetail>(`/api/games/${id}`);
}

export function getGameAnalysis(id: number): Promise<GameAnalysisResponse> {
  return fetchJSON<GameAnalysisResponse>(`/api/games/${id}/analysis`);
}

export function getPlayerStats(name: string): Promise<PlayerStats> {
  return fetchJSON<PlayerStats>(
    `/api/players/${encodeURIComponent(name)}/stats`
  );
}

export function getLiveState(): Promise<LiveStateResponse> {
  return fetchJSON<LiveStateResponse>("/api/live");
}
