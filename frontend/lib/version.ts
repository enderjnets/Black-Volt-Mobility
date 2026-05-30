export interface VersionEntry {
  version: string;
  date: string;
  title: string;
  changes: string[];
}

export const CURRENT_VERSION = "0.0.1";

export const CHANGELOG: VersionEntry[] = [
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
