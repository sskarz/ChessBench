"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import type { ConnectionStatus } from "@/hooks/useWebSocket";

const WS_STATUS_COLORS: Record<ConnectionStatus, string> = {
  connected: "bg-[var(--ws-connected)]",
  connecting: "bg-[var(--ws-connecting)]",
  disconnected: "bg-[var(--ws-disconnected)]",
};

interface NavigationProps {
  wsStatus?: ConnectionStatus;
  gameId?: number | null;
}

export default function Navigation({ wsStatus = "disconnected", gameId }: NavigationProps) {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-3 group">
          <Image
            src="/logo.png"
            alt="ChessBench logo"
            width={32}
            height={32}
            className="invert"
          />
          <span className="font-[family-name:var(--font-display)] text-lg font-bold tracking-tight text-accent">
            ChessBench
          </span>
        </Link>

        <div className="flex items-center gap-6">
          <Link
            href="/"
            className={`flex items-center gap-2 text-sm font-medium transition-colors ${
              pathname === "/"
                ? "text-foreground"
                : "text-secondary hover:text-foreground"
            }`}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                WS_STATUS_COLORS[wsStatus]
              } ${wsStatus === "connected" ? "animate-pulse" : ""}`}
            />
            Live
          </Link>

          {gameId && (
            <motion.span
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              className="hidden sm:block font-[family-name:var(--font-mono)] text-xs text-muted"
            >
              Game #{gameId}
            </motion.span>
          )}
        </div>
      </div>
    </nav>
  );
}
