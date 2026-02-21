"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useGameState } from "@/hooks/useGameState";
import { startTournament, resumeTournament, startBenchmark } from "@/lib/api";
import Navigation from "@/components/Navigation";
import LiveBoard from "@/components/LiveBoard";
import EvalBar from "@/components/EvalBar";
import PlayerCard from "@/components/PlayerCard";
import Scoreboard from "@/components/Scoreboard";
import GameMiniCard from "@/components/GameMiniCard";
import GameDetailPanel from "@/components/GameDetailPanel";

export default function Home() {
  const {
    wsStatus,
    games,
    selectedGameId,
    selectedGame,
    standings,
    tournamentStatus,
    error,
    selectGame,
  } = useGameState();

  const [isStarting, setIsStarting] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [isBenchmarking, setIsBenchmarking] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const tournamentBusy =
    isStarting ||
    isResuming ||
    isBenchmarking ||
    tournamentStatus === "running" ||
    tournamentStatus === "queued";

  async function handleStartTournament() {
    setIsStarting(true);
    setStartError(null);
    try {
      await startTournament(1);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to start tournament");
    } finally {
      setIsStarting(false);
    }
  }

  async function handleResumeTournament() {
    setIsResuming(true);
    setStartError(null);
    try {
      await resumeTournament();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to resume tournament");
    } finally {
      setIsResuming(false);
    }
  }

  async function handleStartBenchmark() {
    setIsBenchmarking(true);
    setStartError(null);
    try {
      await startBenchmark(10);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to start benchmark");
    } finally {
      setIsBenchmarking(false);
    }
  }

  // All games in state (active + recently ended) for the grid
  const allGames = useMemo(
    () => Object.values(games),
    [games],
  );
  const activeGames = useMemo(
    () => allGames.filter((g) => g.isActive),
    [allGames],
  );
  const hasMultipleGames = allGames.length > 1;

  // Grid column class based on game count
  const gridColsClass = allGames.length >= 5
    ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
    : "grid-cols-1 sm:grid-cols-2";

  // Derive data from selected game
  const sg = selectedGame;
  const moves = sg?.moves ?? [];
  const lastMove = moves.length > 0 ? moves[moves.length - 1] : null;
  const lastMoveUci = lastMove?.move_uci;
  const evalCp = lastMove?.eval_cp ?? null;
  const evalMate = lastMove?.eval_mate ?? null;
  const winPctWhite = lastMove?.win_pct_white ?? 50;

  const whiteMoves = moves.filter((m) => m.color === "white");
  const blackMoves = moves.filter((m) => m.color === "black");
  const whiteAccuracy =
    whiteMoves.length > 0
      ? whiteMoves.reduce((s, m) => s + m.accuracy, 0) / whiteMoves.length
      : undefined;
  const blackAccuracy =
    blackMoves.length > 0
      ? blackMoves.reduce((s, m) => s + m.accuracy, 0) / blackMoves.length
      : undefined;
  const whiteAvgCpl = lastMove?.white_avg_cpl;
  const blackAvgCpl = lastMove?.black_avg_cpl;

  const hasActiveGame = sg != null;
  const noGamesAtAll = Object.keys(games).length === 0;

  return (
    <div className="min-h-screen bg-background">
      <Navigation wsStatus={wsStatus} gameId={sg?.gameId ?? null} />

      {/* Reconnecting banner */}
      <AnimatePresence>
        {wsStatus === "disconnected" && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-b border-[var(--ws-disconnected)] bg-[var(--ws-disconnected)]/10 text-center text-xs text-[var(--ws-disconnected)]"
          >
            <div className="py-1.5">
              Disconnected from server — reconnecting...
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {/* Tournament status header */}
        {tournamentStatus !== "idle" && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6"
          >
            {tournamentStatus === "running" && activeGames.length > 0 && (
              <p className="text-sm text-secondary">
                {activeGames.length} game{activeGames.length !== 1 ? "s" : ""} in progress
                {sg && (
                  <span className="ml-2 text-foreground">
                    Round {sg.round}
                  </span>
                )}
              </p>
            )}
            {tournamentStatus === "running" && activeGames.length === 0 && sg && !sg.isActive && (
              <p className="text-sm text-secondary">
                Game ended: <span className="text-foreground font-medium">{sg.result}</span>
              </p>
            )}
            {tournamentStatus === "completed" && (
              <p className="text-sm text-[var(--clr-best)]">
                Tournament complete
              </p>
            )}
            {tournamentStatus === "error" && (
              <p className="text-sm text-[var(--clr-blunder)]">
                Error: {error}
              </p>
            )}
          </motion.div>
        )}

        {/* Multi-game: responsive grid + detail panel below */}
        {hasMultipleGames ? (
          <div className="space-y-6">
            {/* Game card grid */}
            <div className={`grid gap-4 ${gridColsClass}`}>
              {allGames.map((game) => (
                <GameMiniCard
                  key={game.gameId}
                  game={game}
                  isSelected={game.gameId === selectedGameId}
                  onClick={() => selectGame(game.gameId)}
                />
              ))}
            </div>

            {/* Selected game detail panel */}
            {sg && (
              <motion.div
                key={sg.gameId}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-border bg-surface/50 p-4"
              >
                <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-secondary">
                  {sg.white} vs {sg.black}
                  {!sg.isActive && sg.result && (
                    <span className="ml-2 text-foreground">{sg.result}</span>
                  )}
                </p>
                <GameDetailPanel gameId={sg.gameId} moves={sg.moves} />
              </motion.div>
            )}
          </div>
        ) : (
          /* Single game or idle: original layout */
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            {/* Left column: board */}
            <div className="flex gap-2">
              <div className="hidden sm:block" style={{ height: "100%" }}>
                <EvalBar evalCp={evalCp} winPctWhite={winPctWhite} evalMate={evalMate} />
              </div>
              <div className="flex-1 space-y-3">
                {sg?.black && (
                  <PlayerCard
                    name={sg.black}
                    color="black"
                    accuracy={blackAccuracy}
                    avgCpl={blackAvgCpl}
                    isActive={sg.isActive && lastMove?.color === "white"}
                    thinkTimeMs={blackMoves.length > 0 ? blackMoves[blackMoves.length - 1].think_time_ms : undefined}
                  />
                )}

                {hasActiveGame ? (
                  <LiveBoard fen={sg!.fen} lastMoveUci={lastMoveUci} />
                ) : null}

                {sg?.white && (
                  <PlayerCard
                    name={sg.white}
                    color="white"
                    accuracy={whiteAccuracy}
                    avgCpl={whiteAvgCpl}
                    isActive={sg.isActive && lastMove?.color === "black"}
                    thinkTimeMs={whiteMoves.length > 0 ? whiteMoves[whiteMoves.length - 1].think_time_ms : undefined}
                  />
                )}

                {/* Idle state */}
                {noGamesAtAll && (
                  <div className="flex flex-col items-center justify-center rounded-lg border border-border bg-surface p-12 text-center">
                    <p className="font-[family-name:var(--font-display)] text-lg font-semibold text-secondary">
                      No active game
                    </p>
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        onClick={handleStartTournament}
                        disabled={tournamentBusy}
                        className="rounded-lg bg-accent px-6 py-2.5 font-[family-name:var(--font-display)] text-sm font-semibold text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isStarting ? (
                          <span className="flex items-center gap-2">
                            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                            Starting...
                          </span>
                        ) : (
                          "Start Tournament"
                        )}
                      </button>
                      <button
                        onClick={handleStartBenchmark}
                        disabled={tournamentBusy}
                        className="rounded-lg bg-[var(--clr-best)] px-6 py-2.5 font-[family-name:var(--font-display)] text-sm font-semibold text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isBenchmarking ? (
                          <span className="flex items-center gap-2">
                            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                            Benchmarking...
                          </span>
                        ) : (
                          "Start Benchmark"
                        )}
                      </button>
                      {(tournamentStatus === "idle" || tournamentStatus === "error" || tournamentStatus === "completed") && (
                        <button
                          onClick={handleResumeTournament}
                          disabled={tournamentBusy}
                          className="rounded-lg border border-accent px-6 py-2.5 font-[family-name:var(--font-display)] text-sm font-semibold text-accent transition-all hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isResuming ? (
                            <span className="flex items-center gap-2">
                              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
                              Resuming...
                            </span>
                          ) : (
                            "Resume Tournament"
                          )}
                        </button>
                      )}
                    </div>
                    {startError && (
                      <p className="mt-2 text-xs text-[var(--clr-blunder)]">
                        {startError}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Right column: info panels (single game) */}
            {sg && (
              <GameDetailPanel gameId={sg.gameId} moves={moves} vertical />
            )}
          </div>
        )}

        {/* Scoreboard */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mt-8"
        >
          <h2 className="mb-3 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-secondary">
            Standings
          </h2>
          <Scoreboard standings={standings} />
        </motion.div>
      </main>
    </div>
  );
}
