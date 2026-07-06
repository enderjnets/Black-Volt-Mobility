import type { Metadata, Viewport } from "next";
import { Inter, Rajdhani } from "next/font/google";

import { AnalyticsTracker } from "@/components/bv/AnalyticsTracker";
import { MetaPixel } from "@/components/bv/MetaPixel";
import { LanguageProvider } from "@/lib/i18n";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const rajdhani = Rajdhani({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-rajdhani",
  // The hero H1 is the LCP element; with the default `swap` its final paint waits
  // for this display font, pushing LCP to ~3.6s on throttled mobile. `optional`
  // lets the first (uncached) paint use the metric-adjusted fallback and skips the
  // late swap, so LCP tracks FCP (~0.9s); cached visits still render Rajdhani. CLS
  // stays 0 via Next's adjustFontFallback.
  display: "optional",
});

export const metadata: Metadata = {
  // Absolute base so per-page canonical/OG URLs resolve correctly (override per env).
  metadataBase: new URL(process.env.NEXT_PUBLIC_PUBLIC_ORIGIN || "https://blackvoltmobility.com"),
  title: "Black Volt Mobility — Premium Electric Rides",
  description: "Silent Power. Premium Arrival. Luxury electric chauffeur & airport transfers.",
  openGraph: {
    title: "Black Volt Mobility — Premium Electric Rides",
    description:
      "Silent Power. Premium Arrival. Luxury electric chauffeur, airport & mountain transfers in Denver.",
    type: "website",
    siteName: "Black Volt Mobility",
  },
};

export const viewport: Viewport = {
  themeColor: "#0A0A0F",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${rajdhani.variable}`}>
      <body className="font-sans antialiased">
        <MetaPixel />
        <LanguageProvider>
          <AnalyticsTracker />
          {children}
        </LanguageProvider>
      </body>
    </html>
  );
}
