import type { NextConfig } from "next";

// `npm run build` makes static files in out/, served by `uv run skillradar-web`.
// `npm run dev` sends /api to that server, so both can run side by side.
const dev = process.env.NODE_ENV === "development";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(dev
    ? {
        async rewrites() {
          return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
        },
      }
    : { output: "export" }),
};

export default config;
