"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface EvalPoint {
  move_number: number;
  eval_cp: number | null;
  color?: string;
}

interface EvalChartProps {
  moves: EvalPoint[];
  height?: number;
  activeMoveIndex?: number | null;
}

function clampPawns(cp: number | null): number {
  if (cp == null) return 0;
  return Math.max(-10, Math.min(10, cp / 100));
}

export default function EvalChart({ moves, height = 160, activeMoveIndex }: EvalChartProps) {
  const data = moves.map((m, i) => ({
    idx: i,
    move: m.move_number,
    eval: clampPawns(m.eval_cp),
  }));

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-border bg-surface text-xs text-muted"
        style={{ height }}
      >
        No moves yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="evalGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--clr-best)" stopOpacity={0.3} />
            <stop offset="50%" stopColor="var(--clr-best)" stopOpacity={0} />
            <stop offset="50%" stopColor="var(--clr-blunder)" stopOpacity={0} />
            <stop offset="100%" stopColor="var(--clr-blunder)" stopOpacity={0.3} />
          </linearGradient>
        </defs>
        <XAxis dataKey="move" hide />
        <YAxis domain={[-10, 10]} hide />
        <ReferenceLine y={0} stroke="var(--border-light)" strokeDasharray="3 3" />
        {activeMoveIndex != null && (
          <ReferenceLine
            x={activeMoveIndex}
            stroke="var(--accent)"
            strokeWidth={1.5}
          />
        )}
        <Tooltip
          contentStyle={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 12,
            fontFamily: "var(--font-mono)",
          }}
          labelFormatter={(val) => `Move ${data[val as number]?.move ?? val}`}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(val: any) => [`${val >= 0 ? "+" : ""}${Number(val).toFixed(2)}`, "Eval"]}
        />
        <Area
          type="monotone"
          dataKey="eval"
          stroke="var(--text-secondary)"
          strokeWidth={1.5}
          fill="url(#evalGrad)"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
