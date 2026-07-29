import type { Metadata } from "next";

import { Booking } from "@/components/bv/web/Booking";

// Same duplicate-canonical exposure as the homepage had: www and the apex both answer 200.
export const metadata: Metadata = { alternates: { canonical: "/book" } };

export default function Page() {
  return <Booking />;
}
