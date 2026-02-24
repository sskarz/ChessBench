import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Runtime proxy: rewrites /api/* and /health requests to the backend.
 * Reads BACKEND_URL at runtime (not build time), so it works on any
 * hosting provider without needing NEXT_PUBLIC_* build args.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Don't proxy Next.js API routes (e.g. /api/config) — only backend routes.
  if (pathname === "/api/config") {
    return NextResponse.next();
  }

  const backendUrl = (
    process.env.BACKEND_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  const target = new URL(
    `${pathname}${request.nextUrl.search}`,
    backendUrl,
  );

  return NextResponse.rewrite(target);
}

export const config = {
  matcher: ["/api/:path*", "/health"],
};
