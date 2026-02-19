"use client";

import { useEffect, useState, useCallback, use } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { Chess } from "chess.js";
import { getGame, getGameAnalysis } from "@/lib/api";
import type { GameDetail, MoveAnalysisEntry } from "@/lib/types";
import { CLASSIFICATION_COLORS, CLASSIFICATION_ICONS, type MoveClassification } from "@/lib/types";
import Navigation from "@/components/Navigation";
import LiveBoard from "@/components/LiveBoard";
import EvalChart from "@/components/EvalChart";
import AccuracyChart from "@/components/AccuracyChart";
import EvalBar from "@/components/EvalBar";

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

function winPctFromCp(cp: number | null): number {
  if (cp == null) return 50;
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
}

export default function GamePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const gameId = parseInt(id, 10);

  const [game, setGame] = useState<GameDetail | null>(null);
  const [analysis, setAnalysis] = useState<MoveAnalysisEntry[]>([]);
  const [currentIdx, setCurrentIdx] = useState(-1); // -1 = starting position
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [g, a] = await Promise.all([
          getGame(gameId),
          getGameAnalysis(gameId),
        ]);
        setGame(g);
        setAnalysis(a.moves);
        setCurrentIdx(a.moves.length - 1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load game");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [gameId]);

  const goTo = useCallback(
    (idx: number) => setCurrentIdx(Math.max(-1, Math.min(idx, analysis.length - 1))),
    [analysis.length]
  );

  // Keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") goTo(currentIdx - 1);
      else if (e.key === "ArrowRight") goTo(currentIdx + 1);
      else if (e.key === "Home") goTo(-1);
      else if (e.key === "End") goTo(analysis.length - 1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [currentIdx, goTo, analysis.length]);

  const currentFen =
    currentIdx >= 0 && analysis[currentIdx]
      ? analysis[currentIdx].fen_after
      : STARTING_FEN;

  const currentMove = currentIdx >= 0 ? analysis[currentIdx] : null;
  const evalCp = currentMove?.eval_after_cp ?? null;
  const winPct = winPctFromCp(evalCp);

  // PGN download
  function downloadPgn() {
    if (!game) return;
    const blob = new Blob([game.pgn], { type: "application/x-chess-pgn" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `game-${game.id}.pgn`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex items-center justify-center py-32 text-secondary">
          Loading game...
        </div>
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex flex-col items-center justify-center py-32 text-center">
          <p className="text-lg text-blunder">{error ?? "Game not found"}</p>
          <Link href="/" className="mt-4 text-sm text-accent hover:underline">
            Back to live
          </Link>
        </div>
      </div>
    );
  }

  // Group moves into pairs for the table
  const movePairs: { num: number; white?: MoveAnalysisEntry; black?: MoveAnalysisEntry; wIdx: number; bIdx: number }[] = [];
  for (let i = 0; i < analysis.length; i++) {
    const m = analysis[i];
    if (m.color === "white") {
      movePairs.push({ num: m.move_number, white: m, wIdx: i, bIdx: -1 });
    } else if (movePairs.length > 0 && !movePairs[movePairs.length - 1].black) {
      movePairs[movePairs.length - 1].black = m;
      movePairs[movePairs.length - 1].bIdx = i;
    } else {
      movePairs.push({ num: m.move_number, black: m, wIdx: -1, bIdx: i });
    }
  }

  const whiteMoves = analysis.filter((m) => m.color === "white");
  const blackMoves = analysis.filter((m) => m.color === "black");

  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {/* Game header */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="font-[family-name:var(--font-display)] text-xl font-bold">
              <Link href={`/players/${encodeURIComponent(game.white)}`} className="text-accent hover:underline">
                {game.white}
              </Link>
              <span className="mx-2 text-secondary">vs</span>
              <Link href={`/players/${encodeURIComponent(game.black)}`} className="text-accent hover:underline">
                {game.black}
              </Link>
            </h1>
            <span className="font-[family-name:var(--font-mono)] text-sm text-secondary">
              {game.result}
            </span>
            <span className="text-xs text-muted">
              {game.termination} &middot; {game.moves_count} moves &middot;{" "}
              {game.duration_seconds.toFixed(0)}s
            </span>
          </div>

          {/* Stat summary */}
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatPill label="White Acc" value={`${game.white_accuracy.toFixed(1)}%`} />
            <StatPill label="Black Acc" value={`${game.black_accuracy.toFixed(1)}%`} />
            <StatPill label="White CPL" value={game.white_avg_cpl.toFixed(1)} />
            <StatPill label="Black CPL" value={game.black_avg_cpl.toFixed(1)} />
            <StatPill label="W Blunders" value={String(game.white_blunders)} warn={game.white_blunders > 0} />
            <StatPill label="B Blunders" value={String(game.black_blunders)} warn={game.black_blunders > 0} />
            <StatPill label="W Tokens" value={game.white_tokens.toLocaleString()} />
            <StatPill label="B Tokens" value={game.black_tokens.toLocaleString()} />
            <StatPill label="W Cost" value={`$${game.white_cost_usd.toFixed(4)}`} />
            <StatPill label="B Cost" value={`$${game.black_cost_usd.toFixed(4)}`} />
            <StatPill label="W Illegals" value={String(game.white_illegal_attempts)} warn={game.white_illegal_attempts > 0} />
            <StatPill label="B Illegals" value={String(game.black_illegal_attempts)} warn={game.black_illegal_attempts > 0} />
          </div>
        </motion.div>

        {/* Board + navigation + charts */}
        <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
          {/* Left: board */}
          <div className="space-y-3">
            <div className="flex gap-2">
              <div className="hidden sm:block" style={{ height: "100%" }}>
                <EvalBar evalCp={evalCp} winPctWhite={winPct} />
              </div>
              <div className="flex-1">
                <LiveBoard
                  fen={currentFen}
                  lastMoveUci={currentMove?.move_uci}
                />
              </div>
            </div>

            {/* Navigation controls */}
            <div className="flex items-center justify-center gap-2">
              <NavBtn label="|◀" onClick={() => goTo(-1)} />
              <NavBtn label="◀" onClick={() => goTo(currentIdx - 1)} />
              <span className="mx-2 font-[family-name:var(--font-mono)] text-xs text-secondary">
                {currentIdx + 1} / {analysis.length}
              </span>
              <NavBtn label="▶" onClick={() => goTo(currentIdx + 1)} />
              <NavBtn label="▶|" onClick={() => goTo(analysis.length - 1)} />
              <button
                onClick={downloadPgn}
                className="ml-4 rounded border border-border px-3 py-1 text-xs text-secondary hover:bg-surface-hover transition-colors"
              >
                Download PGN
              </button>
            </div>

            {/* Charts */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-border bg-surface p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-secondary">
                  Evaluation
                </p>
                <EvalChart
                  moves={analysis.map((m) => ({
                    move_number: m.move_number,
                    eval_cp: m.eval_after_cp,
                  }))}
                  height={140}
                  activeMoveIndex={currentIdx >= 0 ? currentIdx : null}
                />
              </div>
              <div className="rounded-lg border border-border bg-surface p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-secondary">
                  Centipawn Loss
                </p>
                <AccuracyChart moves={analysis} height={140} />
              </div>
            </div>
          </div>

          {/* Right: move table */}
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <div className="sticky top-0 z-10 border-b border-border bg-surface px-3 py-2">
              <span className="font-[family-name:var(--font-display)] text-xs font-semibold uppercase tracking-wider text-secondary">
                Move Analysis
              </span>
            </div>
            <div className="max-h-[600px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-surface-2">
                  <tr className="border-b border-border text-left text-secondary">
                    <th className="px-2 py-1.5">#</th>
                    <th className="px-2 py-1.5">Move</th>
                    <th className="px-2 py-1.5">CPL</th>
                    <th className="px-2 py-1.5">Class</th>
                    <th className="px-2 py-1.5">Best</th>
                    <th className="px-2 py-1.5">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.map((m, i) => {
                    const cls = m.classification as MoveClassification;
                    const clsColor = CLASSIFICATION_COLORS[cls] ?? "inherit";
                    const icon = CLASSIFICATION_ICONS[cls] ?? "";
                    return (
                      <tr
                        key={i}
                        onClick={() => goTo(i)}
                        className={`cursor-pointer border-b border-border/30 transition-colors hover:bg-surface-hover ${
                          i === currentIdx ? "bg-surface-hover" : ""
                        }`}
                      >
                        <td className="px-2 py-1 font-[family-name:var(--font-mono)] text-muted">
                          {m.move_number}{m.color === "white" ? "." : "..."}
                        </td>
                        <td className="px-2 py-1 font-[family-name:var(--font-mono)]" style={{ color: clsColor }}>
                          {m.move_san}{icon}
                        </td>
                        <td className="px-2 py-1 font-[family-name:var(--font-mono)]">
                          {m.centipawn_loss}
                        </td>
                        <td className="px-2 py-1" style={{ color: clsColor }}>
                          {m.classification}
                        </td>
                        <td className="px-2 py-1 font-[family-name:var(--font-mono)] text-muted">
                          {m.best_move_san ?? "—"}
                        </td>
                        <td className="px-2 py-1 font-[family-name:var(--font-mono)] text-muted">
                          {m.think_time_ms != null ? `${(m.think_time_ms / 1000).toFixed(1)}s` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function StatPill({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded border border-border bg-surface px-3 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`font-[family-name:var(--font-mono)] text-sm ${warn ? "text-[var(--clr-blunder)]" : ""}`}>
        {value}
      </div>
    </div>
  );
}

function NavBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded border border-border px-3 py-1.5 text-sm text-secondary hover:bg-surface-hover transition-colors"
    >
      {label}
    </button>
  );
}
