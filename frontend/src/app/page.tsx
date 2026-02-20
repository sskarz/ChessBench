"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useGameState } from "@/hooks/useGameState";
import { startTournament, resumeTournament } from "@/lib/api";
import Navigation from "@/components/Navigation";
import LiveBoard from "@/components/LiveBoard";
import EvalBar from "@/components/EvalBar";
import EvalChart from "@/components/EvalChart";
import PlayerCard from "@/components/PlayerCard";
import MoveList from "@/components/MoveList";
import Scoreboard from "@/components/Scoreboard";

export default function Home() {
  const {
    wsStatus,
    gameId,
    white,
    black,
    round,
    fen,
    moves,
    isGameActive,
    result,
    standings,
    tournamentStatus,
    error,
  } = useGameState();

  const [isStarting, setIsStarting] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const tournamentBusy =
    isStarting ||
    isResuming ||
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

  const lastMove = moves.length > 0 ? moves[moves.length - 1] : null;
  const lastMoveUci = lastMove?.move_uci;
  const evalCp = lastMove?.eval_cp ?? null;
  const evalMate = lastMove?.eval_mate ?? null;
  const winPctWhite = lastMove?.win_pct_white ?? 50;

  // Build eval chart data from moves
  const evalChartData = moves.map((m) => ({
    move_number: m.move_number,
    eval_cp: m.eval_cp,
    color: m.color,
  }));

  // Derive per-side running stats
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

  return (
    <div className="min-h-screen bg-background">
      <Navigation wsStatus={wsStatus} gameId={gameId} />

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
            {tournamentStatus === "running" && isGameActive && round && (
              <p className="text-sm text-secondary">
                Round {round}
                {white && black && (
                  <span className="ml-2 text-foreground">
                    {white} vs {black}
                  </span>
                )}
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
            {result && !isGameActive && tournamentStatus === "running" && (
              <p className="text-sm text-secondary">
                Game ended: <span className="text-foreground font-medium">{result}</span>
              </p>
            )}
          </motion.div>
        )}

        {/* Main game area — 2 columns on lg */}
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          {/* Left column: board */}
          <div className="flex gap-2">
            {/* Eval bar */}
            <div className="hidden sm:block" style={{ height: "100%" }}>
              <EvalBar evalCp={evalCp} winPctWhite={winPctWhite} evalMate={evalMate} />
            </div>

            {/* Board + player cards */}
            <div className="flex-1 space-y-3">
              {/* Black player (top) */}
              {black && (
                <PlayerCard
                  name={black}
                  color="black"
                  accuracy={blackAccuracy}
                  avgCpl={blackAvgCpl}
                  isActive={isGameActive && lastMove?.color === "white"}
                  thinkTimeMs={blackMoves.length > 0 ? blackMoves[blackMoves.length - 1].think_time_ms : undefined}
                />
              )}

              {/* Board */}
              <LiveBoard fen={fen} lastMoveUci={lastMoveUci} />

              {/* White player (bottom) */}
              {white && (
                <PlayerCard
                  name={white}
                  color="white"
                  accuracy={whiteAccuracy}
                  avgCpl={whiteAvgCpl}
                  isActive={isGameActive && lastMove?.color === "black"}
                  thinkTimeMs={whiteMoves.length > 0 ? whiteMoves[whiteMoves.length - 1].think_time_ms : undefined}
                />
              )}

              {/* Idle state */}
              {!isGameActive && !white && !black && (
                <div className="flex flex-col items-center justify-center rounded-lg border border-border bg-surface p-12 text-center">
                  <p className="font-[family-name:var(--font-display)] text-lg font-semibold text-secondary">
                    No active game
                  </p>
                  <div className="mt-4 flex gap-3">
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

          {/* Right column: info panels */}
          <div className="space-y-4">
            {/* Last move info */}
            {lastMove && (
              <motion.div
                key={moves.length}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="rounded-lg border border-border bg-surface p-3"
              >
                <div className="flex items-center justify-between text-xs text-secondary mb-1">
                  <span>Last move</span>
                  <span className="font-[family-name:var(--font-mono)]">
                    {lastMove.eval_cp != null
                      ? `${lastMove.eval_cp >= 0 ? "+" : ""}${(lastMove.eval_cp / 100).toFixed(2)}`
                      : lastMove.eval_mate != null
                        ? `M${Math.abs(lastMove.eval_mate)}`
                        : ""}
                  </span>
                </div>
                <p className="font-[family-name:var(--font-mono)] text-sm">
                  <span className="text-accent">{lastMove.move_san}</span>
                  <span
                    className="ml-2 text-xs"
                    style={{
                      color:
                        lastMove.classification in
                        {
                          best: 1,
                          excellent: 1,
                          good: 1,
                          inaccuracy: 1,
                          mistake: 1,
                          blunder: 1,
                        }
                          ? `var(--clr-${lastMove.classification})`
                          : undefined,
                    }}
                  >
                    {lastMove.classification}
                  </span>
                  {lastMove.best_move_san && lastMove.classification !== "best" && (
                    <span className="ml-2 text-xs text-muted">
                      best: {lastMove.best_move_san}
                    </span>
                  )}
                </p>
              </motion.div>
            )}

            {/* Eval chart */}
            <div className="rounded-lg border border-border bg-surface p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-secondary">
                Evaluation
              </p>
              <EvalChart moves={evalChartData} height={120} />
            </div>

            {/* Move list */}
            <MoveList moves={moves} />
          </div>
        </div>

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
