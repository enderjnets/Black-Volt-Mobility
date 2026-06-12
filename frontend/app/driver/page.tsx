import type { Metadata } from "next";

import { DriverLanding } from "@/components/bv/driver/DriverLanding";

export const metadata: Metadata = {
  title: "Black Volt Mobility — for licensed operators",
  description:
    "The operating system for the licensed chauffeur. AI-piloted operations, "
    + "compliance-first, more private clients. Free, Operator and Growth plans.",
};

// Served at driver.blackvoltmobility.com via the host rewrite in next.config.js
// (host → /driver). Uses the root layout only (no WebShell, no auth guard).
export default function DriverPage() {
  return <DriverLanding />;
}
