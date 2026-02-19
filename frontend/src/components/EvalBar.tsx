"use client";

interface EvalBarProps {
  evalCp: number | null;
  winPctWhite: number;
  evalMate?: number | null;
}

function formatEval(evalCp: number | null, evalMate?: number | null): string {
  if (evalMate != null && evalMate !== 0) {
    return `M${Math.abs(evalMate)}`;
  }
  if (evalCp == null) return "0.0";
  const pawns = evalCp / 100;
  const sign = pawns >= 0 ? "+" : "";
  return `${sign}${pawns.toFixed(1)}`;
}

export default function EvalBar({ evalCp, winPctWhite, evalMate }: EvalBarProps) {
  // Clamp to 2-98% for visual
  const whiteHeight = Math.max(2, Math.min(98, winPctWhite));

  return (
    <div className="flex h-full w-7 flex-col items-center gap-1">
      <div className="relative flex-1 w-full overflow-hidden rounded-sm bg-[var(--eval-black)]">
        <div
          className="absolute bottom-0 w-full bg-[var(--eval-white)] transition-all duration-500 ease-out"
          style={{ height: `${whiteHeight}%` }}
        />
      </div>
      <span className="font-[family-name:var(--font-mono)] text-[10px] leading-none text-secondary whitespace-nowrap">
        {formatEval(evalCp, evalMate)}
      </span>
    </div>
  );
}
