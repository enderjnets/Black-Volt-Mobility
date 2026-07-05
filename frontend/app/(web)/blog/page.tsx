import type { Metadata } from "next";

import { SoroBlog } from "@/components/bv/web/SoroBlog";
import { SITE_ORIGIN } from "@/lib/seoRoutes";

export const metadata: Metadata = {
  title: "Blog — Black Volt Mobility · Denver Luxury EV Transfers",
  description:
    "Guides and tips for private luxury EV transfers across Denver, DEN airport, and the Colorado mountains — from Black Volt Mobility.",
  alternates: { canonical: "/blog" },
  openGraph: {
    title: "Blog — Black Volt Mobility",
    description:
      "Guides and tips for private luxury EV transfers across Denver, DEN airport, and the Colorado mountains.",
    url: `${SITE_ORIGIN}/blog`,
    type: "website",
  },
};

export default function BlogPage() {
  return (
    <main style={{ maxWidth: 860, margin: "0 auto", padding: "20px 16px 64px" }}>
      <SoroBlog />
    </main>
  );
}
