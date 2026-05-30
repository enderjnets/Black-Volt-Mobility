export interface VersionEntry {
  version: string;
  date: string;
  title: string;
  changes: string[];
}

export const CURRENT_VERSION = "0.2.0";

export const CHANGELOG: VersionEntry[] = [
  {
    version: "0.2.0",
    date: "2026-05-30",
    title: "Driver Dashboard kit (from Claude Design)",
    changes: [
      "Dashboard shell: sidebar + topbar, collapses to an icon rail on mobile.",
      "Overview: KPIs, AI assistant card, today's rides, weekly bars.",
      "Rides: list + month/week Calendar; Clients CRM with search.",
      "Communications inbox: SMS / AI call / AI chat + AI-draft reply.",
      "Rates & brand editor with live fare preview. Bilingual EN/ES.",
    ],
  },
  {
    version: "0.1.0",
    date: "2026-05-30",
    title: "Passenger Web kit (from Claude Design)",
    changes: [
      "Booking flow: pickup/dropoff, route review, fare, Square pay, confirmation.",
      "My Trips: live tracking + flight status (mock data).",
      "Public driver profile /d/[slug] with QR onboarding card.",
      "Google sign-in modal + account (saved addresses, payment, prefs).",
      "Floating AI chat assistant; full design tokens + branded icon.",
    ],
  },
  {
    version: "0.0.1",
    date: "2026-05-29",
    title: "Phase 0 — Bootstrap",
    changes: [
      "New repo: FastAPI + Next.js 14 + Postgres + Redis + Docker stack.",
      "Black Volt brand theme (void black + electric cyan, Rajdhani + Inter).",
      "Bilingual shell: English default + Spanish switcher.",
      "Health endpoint + landing page + version history modal.",
    ],
  },
];
