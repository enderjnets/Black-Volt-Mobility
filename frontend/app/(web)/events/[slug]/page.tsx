import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import EventCta from "@/components/bv/web/EventCta";
import EventViewContent from "@/components/bv/web/EventViewContent";
import RouteTrust from "@/components/bv/web/RouteTrust";
import { SITE_ORIGIN } from "@/lib/seoRoutes";
import { PUBLIC_PROFILE_SLUG } from "@/lib/tenant";

export const dynamic = "force-dynamic";

const API = process.env.INTERNAL_API_URL || "http://localhost:8012";

interface VenueProfile {
  name: string;
  address: string;
  dropoff: string[];
  pickup: string[];
  eats: string[];
  parking_pain: string;
}

interface EventDetail {
  slug: string;
  title: string;
  performer: string | null;
  venue_key: string;
  venue_name: string;
  venue_address: string | null;
  starts_at: string;
  doors_at: string | null;
  about_text: string | null;
  tips_text: string | null;
  status: string;
  event_url: string | null;
  hero_url: string | null;
  venue_profile: VenueProfile;
  passed: boolean;
  flat_price: number;
  one_way_from: number;
  round_trip_price: number | null;
  return_at: string | null;
}

async function getEvent(slug: string): Promise<EventDetail | null> {
  try {
    const r = await fetch(`${API}/api/v1/events/public/${encodeURIComponent(slug)}`, {
      cache: "no-store",
    });
    if (!r.ok) return null;
    return (await r.json()) as EventDetail;
  } catch {
    return null;
  }
}

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", timeZone: "America/Denver",
  });
}

/** Event date/time in America/Denver as {date:"YYYY-MM-DD", time:"HH:MM"} for /book prefill. */
function denverParts(iso: string): { date: string; time: string } {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Denver", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
  const p: Record<string, string> = {};
  for (const part of fmt.formatToParts(new Date(iso))) p[part.type] = part.value;
  const hour = p.hour === "24" ? "00" : p.hour;
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${hour}:${p.minute}` };
}

function bookLink(ev: EventDetail, dir: "to" | "from" | "roundtrip"): string {
  const venue = ev.venue_address || ev.venue_name;
  const p = new URLSearchParams({
    ref: PUBLIC_PROFILE_SLUG,
    utm_source: "events",
    utm_medium: "landing",
    utm_campaign: `event-${ev.slug}`,
  });
  // Prefill the event date so /quote matches the event and applies its fees. Outbound legs
  // arrive ~1h before showtime; the post-show pickup uses the expected end.
  const arrive = denverParts(new Date(new Date(ev.starts_at).getTime() - 60 * 60 * 1000).toISOString());
  const showEnd = ev.return_at ? denverParts(ev.return_at) : arrive;
  if (dir === "to") {
    p.set("to", venue);
    p.set("date", arrive.date);
    p.set("time", arrive.time);
  } else if (dir === "from") {
    p.set("from", venue);
    p.set("date", showEnd.date);
    p.set("time", showEnd.time);
  } else {
    p.set("to", venue);
    p.set("rt", "1");
    p.set("date", arrive.date);
    p.set("time", arrive.time);
    if (ev.return_at) p.set("return_at", ev.return_at);
  }
  return `/book?${p.toString()}`;
}

function eventBookLink(ev: EventDetail): string {
  // Dedicated round-trip event flow: reuse the shared ref/utm attribution, drop the
  // one-way trip params, and retarget to the event's own booking page.
  const q = bookLink(ev, "roundtrip").split("?")[1] ?? "";
  const p = new URLSearchParams(q);
  ["to", "from", "rt", "date", "time", "return_at"].forEach((k) => p.delete(k));
  return `/events/${ev.slug}/book?${p.toString()}`;
}

export async function generateMetadata(
  { params }: { params: { slug: string } },
): Promise<Metadata> {
  const ev = await getEvent(params.slug);
  if (!ev) return { title: "Event | Black Volt Mobility" };
  const desc =
    (ev.about_text || "").split("\n").filter(Boolean)[0]?.slice(0, 155) ||
    `Round-trip ride to ${ev.title} at ${ev.venue_name} — your driver waits during the show and brings you home, no surge. A 1/3 deposit books it.`;
  const title = `${ev.title} — Ride to ${ev.venue_name} | Black Volt Mobility`;
  const url = `${SITE_ORIGIN}/events/${ev.slug}`;
  return {
    title,
    description: desc,
    alternates: { canonical: url },
    openGraph: {
      title, description: desc, url, type: "website",
      images: ev.hero_url ? [{ url: ev.hero_url }] : undefined,
    },
  };
}

const SECTION: React.CSSProperties = { maxWidth: 760, margin: "0 auto", padding: "0 20px" };
const H2: React.CSSProperties = { fontSize: 22, fontWeight: 700, marginBottom: 12 };

function TipList({ items }: { items: string[] }) {
  return (
    <ul style={{ display: "grid", gap: 10, paddingLeft: 0, listStyle: "none", margin: 0 }}>
      {items.map((it, i) => (
        <li key={i} style={{ display: "flex", gap: 10, color: "var(--silver)", fontSize: 15, lineHeight: 1.5 }}>
          <span style={{ color: "var(--volt)", flexShrink: 0 }}>▸</span>
          <span>{it}</span>
        </li>
      ))}
    </ul>
  );
}

export default async function EventPage({ params }: { params: { slug: string } }) {
  const ev = await getEvent(params.slug);
  if (!ev) notFound();

  if (ev.passed) {
    return (
      <main style={{ padding: "80px 0" }}>
        <div style={{ ...SECTION, textAlign: "center" }}>
          <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>{ev.title}</h1>
          <p style={{ color: "var(--fg3)", fontSize: 16, marginBottom: 24 }}>
            This event has passed. We&apos;d still love to drive you — book a ride or see what&apos;s coming up.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <Link href="/book" style={ctaStyle(true)}>Book a ride</Link>
            <Link href="/#events" style={ctaStyle(false)}>Upcoming events</Link>
          </div>
        </div>
      </main>
    );
  }

  const paras = (ev.about_text || "").split("\n").filter((p) => p.trim());
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Event",
    name: ev.title,
    startDate: ev.starts_at,
    eventStatus: "https://schema.org/EventScheduled",
    location: {
      "@type": "Place",
      name: ev.venue_name,
      address: ev.venue_address || ev.venue_profile.address,
    },
    ...(ev.hero_url ? { image: [ev.hero_url] } : {}),
    offers: {
      "@type": "Offer",
      name: "Black Volt ride to the event",
      price: String(ev.round_trip_price ?? ev.flat_price),
      priceCurrency: "USD",
      url: `${SITE_ORIGIN}/events/${ev.slug}`,
      availability: "https://schema.org/InStock",
    },
  };

  // Lead the landing with the reservation deposit (1/3 of the round-trip estimate) instead
  // of the full total — the total stays visible as a breakdown.
  const rtTotal = Math.round(ev.round_trip_price ?? ev.flat_price);
  const deposit = Math.round((ev.round_trip_price ?? ev.flat_price) / 3);

  return (
    <main style={{ paddingBottom: 96 }}>
      <script
        type="application/ld+json"
        // Escape "<" so dynamic values (title/venue from the events API or admin edits)
        // can't break out of the script tag with a literal </script>.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />

      {/* Hero */}
      <section style={{ position: "relative", overflow: "hidden", marginBottom: 40 }}>
        <div
          style={{
            minHeight: 360,
            background: ev.hero_url
              ? `linear-gradient(180deg, rgba(10,10,15,0.25), rgba(10,10,15,0.55), rgba(10,10,15,0.92)), url(${ev.hero_url}) center/cover`
              : "linear-gradient(135deg, var(--obsidian-3), var(--volt))",
            display: "flex",
            alignItems: "flex-end",
          }}
        >
          <div style={{ ...SECTION, padding: "0 20px 32px", width: "100%" }}>
            <EventCta variant="badge" deposit={deposit} total={rtTotal} />
            <h1 style={{ fontSize: 34, fontWeight: 800, lineHeight: 1.1, textShadow: "0 2px 12px rgba(0,0,0,0.6)" }}>
              {ev.title}
            </h1>
            <p style={{ fontSize: 16, marginTop: 8, color: "#fff", textShadow: "0 2px 8px rgba(0,0,0,0.6)" }}>
              {ev.venue_name} · {fmtWhen(ev.starts_at)}
            </p>
          </div>
        </div>
      </section>

      {/* Primary CTA */}
      <section style={{ ...SECTION, marginBottom: 40 }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <EventCta variant="primary" deposit={deposit} total={rtTotal} href={eventBookLink(ev)} />
        </div>
      </section>

      {/* About */}
      {paras.length > 0 && (
        <section style={{ ...SECTION, marginBottom: 40 }}>
          <h2 style={H2}>About the show</h2>
          {paras.map((p, i) => (
            <p key={i} style={{ color: "var(--silver)", fontSize: 15, lineHeight: 1.6, marginBottom: 12 }}>
              {p}
            </p>
          ))}
        </section>
      )}

      {/* Getting there */}
      <section style={{ ...SECTION, marginBottom: 40 }}>
        <h2 style={H2}>Getting there — drop-off before the show</h2>
        <TipList items={ev.venue_profile.dropoff} />
      </section>

      {/* Getting home */}
      <section style={{ ...SECTION, marginBottom: 40 }}>
        <h2 style={H2}>Getting home — pickup after the show</h2>
        <TipList items={ev.venue_profile.pickup} />
      </section>

      {/* Eats */}
      {ev.venue_profile.eats.length > 0 && (
        <section style={{ ...SECTION, marginBottom: 40 }}>
          <h2 style={H2}>Bars &amp; restaurants nearby</h2>
          <TipList items={ev.venue_profile.eats} />
        </section>
      )}

      {/* Why Black Volt */}
      <section style={{ ...SECTION, marginBottom: 40 }}>
        <h2 style={H2}>Why ride with Black Volt</h2>
        <p style={{ color: "var(--silver)", fontSize: 15, lineHeight: 1.6, marginBottom: 20 }}>
          {ev.venue_profile.parking_pain}
        </p>
        <RouteTrust />
      </section>

      {/* Bottom CTA */}
      <section style={{ ...SECTION }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <EventCta variant="primary" deposit={deposit} total={rtTotal} href={eventBookLink(ev)} />
        </div>
      </section>
      <EventCta variant="sticky" deposit={deposit} href={eventBookLink(ev)} />
      <EventViewContent slug={ev.slug} title={ev.title} value={rtTotal} />
    </main>
  );
}

function ctaStyle(primary: boolean): React.CSSProperties {
  return {
    padding: "13px 26px",
    borderRadius: "var(--radius-full)",
    fontWeight: 700,
    fontSize: 15,
    textDecoration: "none",
    background: primary ? "var(--volt)" : "transparent",
    color: primary ? "var(--obsidian-3)" : "var(--silver)",
    border: primary ? "none" : "1px solid var(--line-strong)",
  };
}
