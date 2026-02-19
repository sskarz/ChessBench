"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
  LabelList,
} from "recharts";
import {
  CLASSIFICATION_COLORS,
  type MoveClassification,
  type AccuracyDistribution,
} from "@/lib/types";

interface AccuracyDistributionChartProps {
  distribution: AccuracyDistribution;
  height?: number;
}

const CATEGORIES: MoveClassification[] = [
  "best",
  "excellent",
  "good",
  "inaccuracy",
  "mistake",
  "blunder",
];

export default function AccuracyDistributionChart({
  distribution,
  height = 220,
}: AccuracyDistributionChartProps) {
  const total = distribution.total_moves || 1;
  const data = CATEGORIES.map((cat) => ({
    name: cat.charAt(0).toUpperCase() + cat.slice(1),
    count: distribution[cat],
    pct: ((distribution[cat] / total) * 100).toFixed(1),
    classification: cat,
  }));

  if (distribution.total_moves === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-border bg-surface text-xs text-muted"
        style={{ height }}
      >
        No move data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        margin={{ top: 16, right: 8, bottom: 0, left: 8 }}
      >
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11, fill: "var(--text-secondary)" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis hide />
        <Tooltip
          contentStyle={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 12,
            fontFamily: "var(--font-mono)",
          }}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(val: any, _name: any, props: any) => [
            `${val} moves (${props?.payload?.pct ?? 0}%)`,
            "Count",
          ]}
        />
        <Bar dataKey="count" isAnimationActive={false} radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={CLASSIFICATION_COLORS[entry.classification]}
            />
          ))}
          <LabelList
            dataKey="pct"
            position="top"
            style={{ fontSize: 10, fill: "var(--text-secondary)" }}
            formatter={(val: unknown) => `${val}%`}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
