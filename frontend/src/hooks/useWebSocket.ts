"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WSEvent } from "@/lib/types";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

interface UseWebSocketOptions {
  url: string;
  onMessage: (event: WSEvent) => void;
  enabled?: boolean;
}

export function useWebSocket({
  url,
  onMessage,
  enabled = true,
}: UseWebSocketOptions) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled) return;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      retriesRef.current = 0;
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data) as WSEvent;
        onMessageRef.current(data);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
      // exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s max
      const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
      retriesRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url, enabled]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { status };
}
