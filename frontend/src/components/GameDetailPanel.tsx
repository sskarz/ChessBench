"use client";

import { motion } from "motion/react";
import EvalChart from "./EvalChart";
import MoveList from "./MoveList";
import type { MoveEvent } from "@/lib/types";

interface GameDetailPanelProps {
  gameId: number;
  moves: MoveEvent[];
  vertical?: boolean;
}

export default function GameDetailPanel({ gameId, moves, vertical = false }: GameDetailPanelProps) {
  const lastMove = moves.length > 0 ? moves[moves.length - 1] : null;

  const evalChartData = moves.map((m) => ({
    move_number: m.move_number,
    eval_cp: m.eval_cp,
    color: m.color,
  }));

  return (
    <div className={vertical ? "space-y-4" : "grid gap-4 sm:grid-cols-3"}>
      {/* Last move info */}
      <div>
        {lastMove ? (
          <motion.div
            key={`${gameId}-${moves.length}`}
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
                    { best: 1, excellent: 1, good: 1, inaccuracy: 1, mistake: 1, blunder: 1 }
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
        ) : (
          <div className="rounded-lg border border-border bg-surface p-3 text-xs text-muted text-center">
            Waiting for moves...
          </div>
        )}
      </div>

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
  );
}
