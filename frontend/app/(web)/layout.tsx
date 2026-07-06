import type { Metadata } from "next";

import { WebShell } from "@/components/bv/web/WebShell";

// The passenger PWA (apex host) links its own manifest + Apple home-screen icon.
export const metadata: Metadata = {
  manifest: "/manifest-client.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Black Volt",
  },
  icons: { apple: "/icons/apple-touch-icon.png" },
  other: { "mobile-web-app-capable": "yes" },
};

export default function WebLayout({ children }: { children: React.ReactNode }) {
  return <WebShell>{children}</WebShell>;
}
