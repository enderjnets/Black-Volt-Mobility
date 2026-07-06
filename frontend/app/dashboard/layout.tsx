import type { Metadata } from "next";

import { AuthGuard } from "@/components/bv/dash/AuthGuard";
import { DashShell } from "@/components/bv/dash/DashShell";

// The driver PWA (app. host) links its own manifest + Apple home-screen icon.
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

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <DashShell>{children}</DashShell>
    </AuthGuard>
  );
}
