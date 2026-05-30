/** @type {import('next').NextConfig} */
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://localhost:8012";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${INTERNAL_API_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
