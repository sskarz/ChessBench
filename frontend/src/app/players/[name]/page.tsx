"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { getPlayerStats, getPlayerAccuracyDistribution } from "@/lib/api";
import type { PlayerStats, AccuracyDistribution } from "@/lib/types";
import Navigation from "@/components/Navigation";
import AccuracyDistributionChart from "@/components/AccuracyDistributionChart";

export default function PlayerPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = use(params);
  const playerName = decodeURIComponent(name);

  const [stats, setStats] = useState<PlayerStats | null>(null);
  const [distribution, setDistribution] = useState<AccuracyDistribution | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [s, d] = await Promise.all([
          getPlayerStats(playerName),
          getPlayerAccuracyDistribution(playerName),
        ]);
        setStats(s);
        setDistribution(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Player not found");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [playerName]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex items-center justify-center py-32 text-secondary">
          Loading player...
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex flex-col items-center justify-center py-32 text-center">
          <p className="text-lg text-[var(--clr-blunder)]">{error ?? "Player not found"}</p>
          <Link href="/" className="mt-4 text-sm text-accent hover:underline">
            Back to live
          </Link>
        </div>
      </div>
    );
  }

  const fmtElo = (v: number) => (v === 0 ? "--" : Math.round(v).toString());
  const fmtConf = (v: "none" | "low" | "high") => (v === "high" ? "High" : v === "low" ? "Low" : "--");

  const statCards: { label: string; value: string; color?: string }[] = [
    { label: "Elo", value: fmtElo(stats.elo) },
    { label: "Elo Conf", value: fmtConf(stats.elo_confidence) },
    { label: "Elo (White)", value: fmtElo(stats.elo_white) },
    { label: "W Conf", value: fmtConf(stats.elo_white_confidence) },
    { label: "Elo (Black)", value: fmtElo(stats.elo_black) },
    { label: "B Conf", value: fmtConf(stats.elo_black_confidence) },
    { label: "W Qualifying", value: stats.elo_white_qualifying_moves.toString() },
    { label: "B Qualifying", value: stats.elo_black_qualifying_moves.toString() },
    { label: "Games", value: stats.games_played.toString() },
    {
      label: "Record",
      value: `${stats.wins}W / ${stats.losses}L / ${stats.draws}D`,
    },
    {
      label: "Accuracy",
      value: `${stats.avg_accuracy.toFixed(1)}%`,
      color: stats.avg_accuracy >= 80 ? "var(--clr-best)" : stats.avg_accuracy >= 60 ? "var(--clr-good)" : "var(--clr-mistake)",
    },
    { label: "Avg CPL", value: stats.avg_cpl.toFixed(1) },
    {
      label: "Blunder Rate",
      value: stats.blunder_rate.toFixed(2),
      color: stats.blunder_rate > 1 ? "var(--clr-blunder)" : stats.blunder_rate > 0.5 ? "var(--clr-mistake)" : "var(--clr-good)",
    },
    { label: "Tokens", value: stats.total_tokens.toLocaleString() },
    { label: "Cost", value: `$${stats.total_cost_usd.toFixed(4)}` },
  ];

  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
          {/* Player header */}
          <div className="mb-8">
            <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold text-accent">
              {stats.name}
            </h1>
            <p className="mt-1 text-sm text-secondary">
              {stats.provider}
              <span className="mx-1.5 text-muted">/</span>
              <span className="font-[family-name:var(--font-mono)]">{stats.model_id}</span>
            </p>
          </div>

          {/* Benchmark Stats */}
          <h2 className="mb-3 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-secondary">
            Benchmark Stats
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {statCards.map((card, i) => (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="rounded-lg border border-border bg-surface p-4"
              >
                <div className="text-[10px] uppercase tracking-wider text-muted">
                  {card.label}
                </div>
                <div
                  className="mt-1 font-[family-name:var(--font-mono)] text-lg font-semibold"
                  style={card.color ? { color: card.color } : undefined}
                >
                  {card.value}
                </div>
              </motion.div>
            ))}
          </div>

          {/* Accuracy Distribution */}
          {distribution && distribution.total_moves > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="mt-8 rounded-lg border border-border bg-surface p-4"
            >
              <h2 className="mb-3 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-secondary">
                Move Classification Distribution
              </h2>
              <AccuracyDistributionChart distribution={distribution} />
            </motion.div>
          )}

          {/* Back link */}
          <div className="mt-8">
            <Link href="/" className="text-sm text-accent hover:underline">
              &larr; Back to arena
            </Link>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
