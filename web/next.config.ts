import type { NextConfig } from "next";
import { resolve } from "path";

const nextConfig: NextConfig = {
  outputFileTracingRoot: resolve(import.meta.dirname, ".."),
};

export default nextConfig;
