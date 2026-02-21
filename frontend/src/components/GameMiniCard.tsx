"use client";

import LiveBoard from "./LiveBoard";
import EvalBar from "./EvalBar";
import type { SingleGameState } from "@/hooks/useGameState";

interface GameMiniCardProps {
  game: SingleGameState;
  isSelected: boolean;
  onClick: () => void;
}

export default function GameMiniCard({ game, isSelected, onClick }: GameMiniCardProps) {
  const lastMove = game.moves.length > 0 ? game.moves[game.moves.length - 1] : null;
  const evalCp = lastMove?.eval_cp ?? null;
  const evalMate = lastMove?.eval_mate ?? null;
  const winPctWhite = lastMove?.win_pct_white ?? 50;
  const evalDisplay = evalCp != null
    ? `${evalCp >= 0 ? "+" : ""}${(evalCp / 100).toFixed(1)}`
    : evalMate != null
      ? `M${Math.abs(evalMate)}`
      : "";

  // Determine whose turn it is (after last move)
  const isWhiteTurn = !lastMove || lastMove.color === "black";

  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg border bg-surface p-3 text-left transition-all hover:border-accent/50 ${
        isSelected
          ? "border-accent ring-2 ring-accent/30"
          : "border-border"
      }`}
    >
      {/* Black player (top, matching board orientation) */}
      <div className="mb-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 truncate">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#333] border border-border/50" />
          <span className="truncate font-medium text-foreground">{game.black}</span>
          {game.isActive && !isWhiteTurn && (
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
          )}
        </div>
      </div>

      {/* Board + compact eval bar */}
      <div className="flex gap-1.5">
        <div className="shrink-0" style={{ height: "auto" }}>
          <EvalBar evalCp={evalCp} winPctWhite={winPctWhite} evalMate={evalMate} compact />
        </div>
        <div className="flex-1 pointer-events-none">
          <LiveBoard
            fen={game.fen}
            lastMoveUci={lastMove?.move_uci}
          />
        </div>
      </div>

      {/* White player (bottom, matching board orientation) */}
      <div className="mt-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 truncate">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-white border border-border/50" />
          <span className="truncate font-medium text-foreground">{game.white}</span>
          {game.isActive && isWhiteTurn && (
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
          )}
        </div>
      </div>

      {/* Status line: last move classification + eval */}
      {lastMove && (
        <div className="mt-2 flex items-center justify-between border-t border-border/50 pt-1.5 text-[10px]">
          <span className="font-[family-name:var(--font-mono)] text-secondary">
            {game.moves.length}. {lastMove.move_san}
            {lastMove.classification && (
              <span
                className="ml-1"
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
            )}
          </span>
          {evalDisplay && (
            <span className="font-[family-name:var(--font-mono)] text-secondary">
              {evalDisplay}
            </span>
          )}
        </div>
      )}

      {/* Result badge if game is over */}
      {!game.isActive && game.result && (
        <div className="mt-2 rounded bg-surface-raised px-2 py-0.5 text-center text-[10px] font-semibold text-secondary">
          {game.result}
        </div>
      )}
    </button>
  );
}
