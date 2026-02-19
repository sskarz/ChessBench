// ── Move classifications ──────────────────────────────────────────

export type MoveClassification =
  | "best"
  | "excellent"
  | "good"
  | "inaccuracy"
  | "mistake"
  | "blunder";

export const CLASSIFICATION_COLORS: Record<MoveClassification, string> = {
  best: "var(--clr-best)",
  excellent: "var(--clr-excellent)",
  good: "var(--clr-good)",
  inaccuracy: "var(--clr-inaccuracy)",
  mistake: "var(--clr-mistake)",
  blunder: "var(--clr-blunder)",
};

export const CLASSIFICATION_ICONS: Record<MoveClassification, string> = {
  best: "!!",
  excellent: "!",
  good: "",
  inaccuracy: "?!",
  mistake: "?",
  blunder: "??",
};

// ── REST response types ──────────────────────────────────────────

export interface StandingsEntry {
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

export interface GameSummary {
  id: number;
  white: string;
  black: string;
  result: string;
  termination: string;
  moves_count: number;
  white_accuracy: number;
  black_accuracy: number;
  duration_seconds: number;
  completed_at: string | null;
  opening_eco: string | null;
  opening_name: string | null;
}

export interface GameListResponse {
  total: number;
  limit: number;
  offset: number;
  items: GameSummary[];
}

export interface GameDetail extends GameSummary {
  pgn: string;
  white_avg_cpl: number;
  black_avg_cpl: number;
  white_blunders: number;
  black_blunders: number;
  white_mistakes: number;
  black_mistakes: number;
  white_illegal_attempts: number;
  black_illegal_attempts: number;
  white_tokens: number;
  black_tokens: number;
  white_cost_usd: number;
  black_cost_usd: number;
  started_at: string;
}

export interface MoveAnalysisEntry {
  move_number: number;
  color: string;
  move_uci: string;
  move_san: string;
  fen_before: string;
  fen_after: string;
  eval_before_cp: number | null;
  eval_after_cp: number | null;
  best_move_uci: string | null;
  best_move_san: string | null;
  centipawn_loss: number;
  classification: string;
  think_time_ms: number | null;
  tokens_used: number | null;
  illegal_attempts: number;
}

export interface GameAnalysisResponse {
  game_id: number;
  moves: MoveAnalysisEntry[];
}

export interface PlayerStats {
  name: string;
  provider: string;
  model_id: string;
  elo: number;
  games_played: number;
  wins: number;
  losses: number;
  draws: number;
  avg_cpl: number;
  avg_accuracy: number;
  total_tokens: number;
  total_cost_usd: number;
  blunder_rate: number;
}

export interface AccuracyDistribution {
  best: number;
  excellent: number;
  good: number;
  inaccuracy: number;
  mistake: number;
  blunder: number;
  total_moves: number;
}

export interface LiveStateResponse {
  status: "idle" | "running" | "completed" | "error";
  run_id: string | null;
  current_game: {
    game_id: number;
    white: string;
    black: string;
    round: number;
  } | null;
  last_event: Record<string, unknown> | null;
  latest_standings: StandingsEntry[];
  started_at: string | null;
  updated_at: string | null;
  error: string | null;
}

export interface TournamentStartResponse {
  status: string;
  run_id: string;
  rounds: number;
  players: { name: string; provider: string; model: string }[];
}

// ── WebSocket event types ────────────────────────────────────────

export interface GameStartEvent {
  type: "game_start";
  game_id: number;
  white: string;
  black: string;
  round: number;
}

export interface MoveEvent {
  type: "move";
  game_id: number;
  move_number: number;
  color: string;
  move_uci: string;
  move_san: string;
  fen: string;
  eval_cp: number | null;
  eval_mate: number | null;
  best_move_san: string | null;
  cpl: number;
  classification: string;
  win_pct_white: number;
  accuracy: number;
  think_time_ms: number;
  illegal_attempts: number;
  white_avg_cpl: number;
  black_avg_cpl: number;
  pgn_so_far: string;
}

export interface GameEndEvent {
  type: "game_end";
  game_id: number;
  result: string;
  termination: string;
  white_accuracy: number;
  black_accuracy: number;
  standings: StandingsEntry[];
}

export interface TournamentCompleteEvent {
  type: "tournament_complete";
  run_id: string;
  games_played: number;
  standings: StandingsEntry[];
}

export interface TournamentErrorEvent {
  type: "tournament_error";
  run_id: string;
  error: string;
}

export interface TournamentQueuedEvent {
  type: "tournament_queued";
  run_id: string;
}

export type WSEvent =
  | GameStartEvent
  | MoveEvent
  | GameEndEvent
  | TournamentCompleteEvent
  | TournamentErrorEvent
  | TournamentQueuedEvent;
