import type { Metadata } from "next";

// /login is the driver PWA's signed-out entry (app. host), so it carries the same
// driver manifest + Apple icon as the dashboard.
export const metadata: Metadata = {
  manifest: "/manifest-driver.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "BV Driver",
  },
  icons: { apple: "/icons/driver-apple-touch-icon.png" },
  other: { "mobile-web-app-capable": "yes" },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
