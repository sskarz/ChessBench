"use client";

import { useMemo } from "react";
import { Chessboard } from "react-chessboard";

interface LiveBoardProps {
  fen: string;
  lastMoveUci?: string;
  boardOrientation?: "white" | "black";
}

function uciToSquares(uci: string): { from: string; to: string } | null {
  if (!uci || uci.length < 4) return null;
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) };
}

export default function LiveBoard({
  fen,
  lastMoveUci,
  boardOrientation = "white",
}: LiveBoardProps) {
  const squareStyles = useMemo(() => {
    const squares = uciToSquares(lastMoveUci ?? "");
    if (!squares) return {};
    const highlight = { backgroundColor: "rgba(201, 168, 76, 0.25)" };
    return {
      [squares.from]: highlight,
      [squares.to]: highlight,
    };
  }, [lastMoveUci]);

  return (
    <div className="aspect-square w-full">
      <Chessboard
        options={{
          position: fen,
          boardOrientation,
          allowDragging: false,
          animationDurationInMs: 300,
          squareStyles,
          darkSquareStyle: { backgroundColor: "#5a6e4e" },
          lightSquareStyle: { backgroundColor: "#e8dcc8" },
        }}
      />
    </div>
  );
}
