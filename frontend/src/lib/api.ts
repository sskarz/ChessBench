import type {
  StandingsEntry,
  GameListResponse,
  GameDetail,
  GameAnalysisResponse,
  PlayerStats,
  AccuracyDistribution,
  LiveStateResponse,
  BenchmarkStartResponse,
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

export function getPlayerAccuracyDistribution(
  name: string
): Promise<AccuracyDistribution> {
  return fetchJSON<AccuracyDistribution>(
    `/api/players/${encodeURIComponent(name)}/accuracy-distribution`
  );
}

export function getLiveState(): Promise<LiveStateResponse> {
  return fetchJSON<LiveStateResponse>("/api/live");
}

export async function startBenchmark(rounds = 1, playerName?: string): Promise<BenchmarkStartResponse> {
  const body: Record<string, unknown> = { rounds };
  if (playerName) {
    body.player_name = playerName;
  }
  const res = await fetch(`${BASE_URL}/api/benchmark/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const msg =
      res.status === 409
        ? "Benchmark already running"
        : `API ${res.status}: ${res.statusText}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BenchmarkStartResponse>;
}
