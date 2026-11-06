import type { NextConfig } from "next";

// `npm run build` makes the local page in out/, served by `uv run skillradar-web`.
// `npm run build:public` makes the public page in out-public/: it reads JSON files instead
// of the API and lives under a base path, e.g. https://<user>.github.io/skillradar/.
// `npm run dev` sends /api to the local server, so both can run side by side.
const dev = process.env.NODE_ENV === "development";
const publicSite = process.env.NEXT_PUBLIC_DATA_MODE === "static";

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
  ...(publicSite ? { distDir: "out-public", basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "" } : {}),
};

export default config;
