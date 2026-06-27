import type { Metadata } from "next";
import Link from "next/link";

import { SEO_ROUTES, SITE_ORIGIN } from "@/lib/seoRoutes";

export const metadata: Metadata = {
  title: "Routes & Rides — Black Volt Mobility (Denver)",
  description:
    "Private luxury electric chauffeur routes across Denver: airport transfers to DEN, Red Rocks concert rides, and mountain transfers to Vail, Breckenridge & Aspen.",
  alternates: { canonical: "/rides" },
  openGraph: {
    title: "Routes & Rides — Black Volt Mobility",
    description:
      "Airport transfers, Red Rocks concert rides, and mountain transfers in a luxury electric SUV.",
    url: `${SITE_ORIGIN}/rides`,
    type: "website",
  },
};

const fmtPrice = (n: number) => `$${n.toLocaleString("en-US")}`;

export default function RidesHub() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "28px 18px 64px" }}>
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 30,
          fontWeight: 700,
          margin: "0 0 10px",
          color: "var(--arctic)",
        }}
      >
        Popular routes & rides
      </h1>
      <p style={{ fontSize: 16, lineHeight: 1.6, color: "var(--fg2)", margin: "0 0 24px" }}>
        Private door-to-door rides in a luxury electric SUV across the Denver metro and the
        Colorado mountains. Pick a route for details and an instant price — or{" "}
        <Link href="/book" style={{ color: "var(--volt)", textDecoration: "none" }}>
          book any trip
        </Link>
        .
      </p>

      <div style={{ display: "grid", gap: 10 }}>
        {SEO_ROUTES.map((r) => (
          <Link
            key={r.slug}
            href={`/rides/${r.slug}`}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 12,
              padding: "15px 18px",
              background: "var(--obsidian-2)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-lg)",
              textDecoration: "none",
            }}
          >
            <span style={{ display: "grid", gap: 3 }}>
              <span style={{ fontSize: 15.5, fontWeight: 600, color: "var(--arctic)" }}>
                {r.shortLabel}
              </span>
              <span style={{ fontSize: 13, color: "var(--fg3)" }}>
                {r.priceFrom != null ? `from ${fmtPrice(r.priceFrom)}` : "Instant quote"} · ~
                {r.distanceMi} mi
              </span>
            </span>
            <span style={{ color: "var(--volt)", fontWeight: 700, fontSize: 18 }}>→</span>
          </Link>
        ))}
      </div>
    </main>
  );
}
