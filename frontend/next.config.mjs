// Browser calls /api/* on the Next.js server, which proxies to the FastAPI service.
// API_INTERNAL_URL is read at build time (set as a build arg in docker-compose).
const API = process.env.API_INTERNAL_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
export default nextConfig;
