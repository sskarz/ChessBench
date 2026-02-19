"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from "recharts";
import { CLASSIFICATION_COLORS, type MoveClassification } from "@/lib/types";

interface AccuracyChartProps {
  moves: { move_number: number; centipawn_loss: number; classification: string; color: string }[];
  height?: number;
}

export default function AccuracyChart({ moves, height = 160 }: AccuracyChartProps) {
  const data = moves.map((m, i) => ({
    idx: i,
    move: m.move_number,
    cpl: m.centipawn_loss,
    classification: m.classification,
    color: m.color,
  }));

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-border bg-surface text-xs text-muted"
        style={{ height }}
      >
        No analysis data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <XAxis dataKey="move" hide />
        <YAxis hide />
        <Tooltip
          contentStyle={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 12,
            fontFamily: "var(--font-mono)",
          }}
          labelFormatter={(val) => {
            const d = data[val as number];
            return d ? `Move ${d.move} (${d.color})` : `#${val}`;
          }}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(val: any, _name: any, props: any) => [
            `${val} cp — ${props?.payload?.classification ?? ""}`,
            "CPL",
          ]}
        />
        <Bar dataKey="cpl" isAnimationActive={false}>
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={
                CLASSIFICATION_COLORS[
                  entry.classification as MoveClassification
                ] ?? "var(--text-muted)"
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
