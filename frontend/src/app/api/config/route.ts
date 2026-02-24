import { NextResponse } from "next/server";

/**
 * Returns runtime configuration to the browser.
 * This lets the client discover the WebSocket URL without needing
 * NEXT_PUBLIC_* build-time env vars.
 */
export async function GET() {
  const backendUrl = (
    process.env.BACKEND_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  const wsProto = backendUrl.startsWith("https") ? "wss:" : "ws:";
  const host = backendUrl.replace(/^https?:\/\//, "");
  const wsUrl = `${wsProto}//${host}/ws/live`;

  return NextResponse.json({ wsUrl });
}
