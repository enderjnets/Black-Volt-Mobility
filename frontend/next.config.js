/** @type {import('next').NextConfig} */
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://localhost:8012";

// Driver dashboard host: app.blackvoltmobility.com lands directly on /dashboard.
// The public marketing site + booking stay on the apex / www. Add more hosts to
// DASHBOARD_HOSTS (comma-separated env) for staging/other tenants later.
const DASHBOARD_HOSTS = (process.env.DASHBOARD_HOSTS || "app.blackvoltmobility.com")
  .split(",")
  .map((h) => h.trim())
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      beforeFiles: DASHBOARD_HOSTS.map((host) => ({
        source: "/",
        has: [{ type: "host", value: host }],
        destination: "/dashboard",
      })),
      afterFiles: [
        {
          source: "/api/:path*",
          destination: `${INTERNAL_API_URL}/api/:path*`,
        },
        {
          // Owner-uploaded brand assets (logo/photo) served by the backend's
          // /media StaticFiles mount; reachable through the app host.
          source: "/media/:path*",
          destination: `${INTERNAL_API_URL}/media/:path*`,
        },
      ],
    };
  },
};

module.exports = nextConfig;
