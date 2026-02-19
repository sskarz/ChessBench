"use client";

import { useRef, useEffect } from "react";
import { motion } from "motion/react";
import {
  CLASSIFICATION_COLORS,
  CLASSIFICATION_ICONS,
  type MoveClassification,
} from "@/lib/types";
import type { MoveEvent } from "@/lib/types";

interface MoveListProps {
  moves: MoveEvent[];
  onMoveClick?: (index: number) => void;
  activeMoveIndex?: number | null;
}

export default function MoveList({ moves, onMoveClick, activeMoveIndex }: MoveListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [moves.length]);

  // Group into pairs (white, black)
  const pairs: { moveNum: number; white?: MoveEvent; black?: MoveEvent; whiteIdx: number; blackIdx: number }[] = [];
  for (let i = 0; i < moves.length; i++) {
    const m = moves[i];
    if (m.color === "white") {
      pairs.push({ moveNum: m.move_number, white: m, whiteIdx: i, blackIdx: -1 });
    } else {
      if (pairs.length > 0 && !pairs[pairs.length - 1].black) {
        pairs[pairs.length - 1].black = m;
        pairs[pairs.length - 1].blackIdx = i;
      } else {
        pairs.push({ moveNum: m.move_number, black: m, whiteIdx: -1, blackIdx: i });
      }
    }
  }

  return (
    <div className="flex flex-col overflow-y-auto rounded border border-border bg-surface" style={{ maxHeight: 280 }}>
      <div className="sticky top-0 z-10 border-b border-border bg-surface px-3 py-1.5">
        <span className="font-[family-name:var(--font-display)] text-xs font-semibold text-secondary uppercase tracking-wider">
          Moves
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        {pairs.length === 0 && (
          <div className="py-8 text-center text-xs text-muted">Waiting for moves...</div>
        )}
        {pairs.map((pair, pIdx) => (
          <motion.div
            key={pIdx}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.15 }}
            className="flex items-center gap-1 py-0.5 px-2 text-sm"
          >
            <span className="w-7 shrink-0 font-[family-name:var(--font-mono)] text-xs text-muted">
              {pair.moveNum}.
            </span>
            {pair.white && (
              <MoveCell
                move={pair.white}
                index={pair.whiteIdx}
                isActive={activeMoveIndex === pair.whiteIdx}
                onClick={onMoveClick}
              />
            )}
            {pair.black && (
              <MoveCell
                move={pair.black}
                index={pair.blackIdx}
                isActive={activeMoveIndex === pair.blackIdx}
                onClick={onMoveClick}
              />
            )}
          </motion.div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}

function MoveCell({
  move,
  index,
  isActive,
  onClick,
}: {
  move: MoveEvent;
  index: number;
  isActive: boolean;
  onClick?: (idx: number) => void;
}) {
  const cls = move.classification as MoveClassification;
  const color = CLASSIFICATION_COLORS[cls] ?? "var(--text-primary)";
  const icon = CLASSIFICATION_ICONS[cls] ?? "";

  return (
    <button
      onClick={() => onClick?.(index)}
      className={`w-20 shrink-0 rounded px-1.5 py-0.5 text-left font-[family-name:var(--font-mono)] text-xs transition-colors hover:bg-surface-hover ${
        isActive ? "bg-surface-hover ring-1 ring-accent" : ""
      }`}
      style={{ color }}
    >
      {move.move_san}
      {icon && (
        <span className="ml-0.5 opacity-60" style={{ color }}>
          {icon}
        </span>
      )}
    </button>
  );
}
