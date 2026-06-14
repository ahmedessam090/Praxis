/** @type {import('next').NextConfig} */
const API = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig = {
  // Proxy /api/* to the FastAPI service so the browser hits one origin (no CORS in dev).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
