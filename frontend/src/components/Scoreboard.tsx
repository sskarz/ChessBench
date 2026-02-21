"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import type { StandingsEntry } from "@/lib/types";

type SortKey = keyof StandingsEntry;

interface ScoreboardProps {
  standings: StandingsEntry[];
}

export default function Scoreboard({ standings }: ScoreboardProps) {
  const [sortKey, setSortKey] = useState<SortKey>("elo");
  const [sortAsc, setSortAsc] = useState(false);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const sorted = [...standings].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
    return sortAsc ? cmp : -cmp;
  });

  const fmtElo = (v: number) => (v === 0 ? "--" : Math.round(v).toString());

  const columns: { key: SortKey; label: string; fmt?: (v: number) => string; align?: string }[] = [
    { key: "elo", label: "Elo", fmt: fmtElo },
    { key: "elo_white", label: "W Elo", fmt: fmtElo },
    { key: "elo_black", label: "B Elo", fmt: fmtElo },
    { key: "wins", label: "W" },
    { key: "losses", label: "L" },
    { key: "draws", label: "D" },
    { key: "avg_accuracy", label: "Acc%", fmt: (v) => v.toFixed(1) },
    { key: "avg_cpl", label: "CPL", fmt: (v) => v.toFixed(1) },
    { key: "blunder_rate", label: "Blunders", fmt: (v) => v.toFixed(2) },
    { key: "total_cost_usd", label: "Cost", fmt: (v) => `$${v.toFixed(4)}` },
  ];

  if (standings.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-muted">
        No standings yet — start a tournament to see results.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-secondary">
            <th className="px-3 py-2.5 font-medium">#</th>
            <th className="px-3 py-2.5 font-medium">Model</th>
            {columns.map((col) => (
              <th
                key={col.key}
                className="cursor-pointer select-none px-3 py-2.5 font-medium hover:text-foreground transition-colors"
                onClick={() => toggleSort(col.key)}
              >
                {col.label}
                {sortKey === col.key && (
                  <span className="ml-1 text-accent">{sortAsc ? "↑" : "↓"}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((entry, i) => (
            <motion.tr
              key={entry.name}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              className="border-b border-border/50 hover:bg-surface-hover transition-colors"
            >
              <td className="px-3 py-2 font-[family-name:var(--font-mono)] text-muted">
                {i + 1}
              </td>
              <td className="px-3 py-2">
                <Link
                  href={`/players/${encodeURIComponent(entry.name)}`}
                  className="font-[family-name:var(--font-display)] font-medium text-accent hover:underline"
                >
                  {entry.name}
                </Link>
              </td>
              {columns.map((col) => (
                <td
                  key={col.key}
                  className="px-3 py-2 font-[family-name:var(--font-mono)] text-xs"
                >
                  {col.fmt
                    ? col.fmt(entry[col.key] as number)
                    : String(entry[col.key])}
                </td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
