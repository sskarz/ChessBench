import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // API proxying is handled by middleware.ts at runtime,
  // so it works on any hosting provider without build-time env vars.
};

export default nextConfig;
