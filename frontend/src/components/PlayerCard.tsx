"use client";

import { motion } from "motion/react";

interface PlayerCardProps {
  name: string;
  color: "white" | "black";
  elo?: number;
  accuracy?: number;
  avgCpl?: number;
  isActive?: boolean;
  thinkTimeMs?: number;
}

export default function PlayerCard({
  name,
  color,
  elo,
  accuracy,
  avgCpl,
  isActive = false,
  thinkTimeMs,
}: PlayerCardProps) {
  const borderColor = color === "white" ? "border-[#e8e6e3]" : "border-[#555]";
  const pieceIcon = color === "white" ? "♔" : "♚";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative rounded-lg border-l-4 ${borderColor} bg-surface p-3`}
    >
      <div className="flex items-center gap-2.5">
        <span className="text-xl leading-none">{pieceIcon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-[family-name:var(--font-display)] text-sm font-semibold">
              {name}
            </span>
            {isActive && (
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
              </span>
            )}
          </div>
          <div className="mt-1 flex gap-3 font-[family-name:var(--font-mono)] text-xs text-secondary">
            {elo != null && <span>{Math.round(elo)} Elo</span>}
            {accuracy != null && <span>{accuracy.toFixed(1)}%</span>}
            {avgCpl != null && <span>{avgCpl.toFixed(1)} CPL</span>}
            {thinkTimeMs != null && (
              <span>{(thinkTimeMs / 1000).toFixed(1)}s</span>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
