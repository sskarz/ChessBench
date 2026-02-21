"use client";

import LiveBoard from "./LiveBoard";
import type { SingleGameState } from "@/hooks/useGameState";

interface GameMiniCardProps {
  game: SingleGameState;
  isSelected: boolean;
  onClick: () => void;
}

export default function GameMiniCard({ game, isSelected, onClick }: GameMiniCardProps) {
  const lastMove = game.moves.length > 0 ? game.moves[game.moves.length - 1] : null;
  const evalCp = lastMove?.eval_cp ?? null;
  const evalDisplay = evalCp != null
    ? `${evalCp >= 0 ? "+" : ""}${(evalCp / 100).toFixed(1)}`
    : lastMove?.eval_mate != null
      ? `M${Math.abs(lastMove.eval_mate)}`
      : "";

  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg border bg-surface p-3 text-left transition-all hover:border-accent/50 ${
        isSelected
          ? "border-accent ring-1 ring-accent/30"
          : "border-border"
      }`}
    >
      {/* Player names */}
      <div className="mb-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 truncate">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-white border border-border/50" />
          <span className="truncate font-medium text-foreground">{game.white}</span>
        </div>
        {evalDisplay && (
          <span className="ml-2 shrink-0 font-[family-name:var(--font-mono)] text-[10px] text-secondary">
            {evalDisplay}
          </span>
        )}
      </div>

      {/* Mini board */}
      <div className="pointer-events-none">
        <LiveBoard
          fen={game.fen}
          lastMoveUci={lastMove?.move_uci}
        />
      </div>

      {/* Black player + move count */}
      <div className="mt-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 truncate">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#333] border border-border/50" />
          <span className="truncate font-medium text-foreground">{game.black}</span>
        </div>
        <span className="ml-2 shrink-0 text-[10px] text-secondary">
          {game.moves.length} moves
        </span>
      </div>

      {/* Result badge if game is over */}
      {!game.isActive && game.result && (
        <div className="mt-2 rounded bg-surface-raised px-2 py-0.5 text-center text-[10px] font-semibold text-secondary">
          {game.result}
        </div>
      )}
    </button>
  );
}
