/** @type {import('next').NextConfig} */
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://localhost:8012";

// Driver dashboard host: app.blackvoltmobility.com lands directly on /dashboard.
// The public marketing site + booking stay on the apex / www. Add more hosts to
// DASHBOARD_HOSTS (comma-separated env) for staging/other tenants later.
const DASHBOARD_HOSTS = (process.env.DASHBOARD_HOSTS || "app.blackvoltmobility.com")
  .split(",")
  .map((h) => h.trim())
  .filter(Boolean);

// Driver subscription landing host: driver.blackvoltmobility.com lands on
// /driver (public, no auth). Same host-rewrite pattern as the dashboard. Baked
// at build time → changing the host requires a rebuild.
const DRIVER_HOSTS = (process.env.DRIVER_HOSTS || "driver.blackvoltmobility.com")
  .split(",")
  .map((h) => h.trim())
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        // Committed static assets (hero photos, route maps). Filenames are stable
        // and content changes ship as new files, so a long edge/browser cache is
        // safe and turns Cloudflare's 4h REVALIDATE into month-long HITs.
        source: "/assets/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=2592000" }],
      },
    ];
  },
  async rewrites() {
    return {
      beforeFiles: [
        ...DASHBOARD_HOSTS.map((host) => ({
          source: "/",
          has: [{ type: "host", value: host }],
          destination: "/dashboard",
        })),
        ...DRIVER_HOSTS.map((host) => ({
          source: "/",
          has: [{ type: "host", value: host }],
          destination: "/driver",
        })),
      ],
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
