import type { Metadata, Viewport } from "next";
import { Inter, Rajdhani } from "next/font/google";

import { AnalyticsTracker } from "@/components/bv/AnalyticsTracker";
import { LanguageProvider } from "@/lib/i18n";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const rajdhani = Rajdhani({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-rajdhani",
});

export const metadata: Metadata = {
  title: "Black Volt Mobility — Premium Electric Rides",
  description: "Silent Power. Premium Arrival. Luxury electric chauffeur & airport transfers.",
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
        <LanguageProvider>
          <AnalyticsTracker />
          {children}
        </LanguageProvider>
      </body>
    </html>
  );
}
