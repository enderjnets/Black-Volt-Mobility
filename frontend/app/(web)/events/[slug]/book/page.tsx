import type { Metadata } from "next";
import { notFound } from "next/navigation";

import EventBooking from "@/components/bv/web/EventBooking";

export const dynamic = "force-dynamic";
// Transactional flow — keep it out of search results (the landing at /events/[slug] is indexable).
export const metadata: Metadata = { robots: { index: false, follow: false } };

const API = process.env.INTERNAL_API_URL || "http://localhost:8012";

export interface BookEvent {
  slug: string;
  title: string;
  venue_name: string;
  venue_address: string | null;
  starts_at: string;
  return_at: string;
  round_trip_price: number | null;
  flat_price: number;
  hero_url: string | null;
  passed: boolean;
}

async function getEvent(slug: string): Promise<BookEvent | null> {
  try {
    const r = await fetch(`${API}/api/v1/events/public/${encodeURIComponent(slug)}`, {
      cache: "no-store",
    });
    if (!r.ok) return null;
    return (await r.json()) as BookEvent;
  } catch {
    return null;
  }
}

export default async function EventBookPage({ params }: { params: { slug: string } }) {
  const ev = await getEvent(params.slug);
  if (!ev || ev.passed) notFound();
  return <EventBooking ev={ev} />;
}
