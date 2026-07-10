"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { listPublicEvents, PublicEvent } from "@/lib/events";
import { useI18n } from "@/lib/i18n";

function dateBadge(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", timeZone: "America/Denver",
  });
}

export default function UpcomingEvents() {
  const { t } = useI18n();
  const [events, setEvents] = useState<PublicEvent[] | null>(null);

  useEffect(() => {
    listPublicEvents()
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  // Invisible until there is something to show (no skeleton, no empty state).
  if (!events || events.length === 0) return null;

  return (
    <section id="events" style={{ marginBottom: 56 }}>
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 26,
          color: "var(--arctic)",
          margin: "0 0 16px",
        }}
      >
        {t("home.events.title")}
      </h2>
      <div
        style={{
          display: "flex",
          gap: 14,
          overflowX: "auto",
          scrollSnapType: "x mandatory",
          paddingBottom: 6,
          WebkitOverflowScrolling: "touch",
        }}
      >
        {events.map((e) => (
          <Link
            key={e.slug}
            href={`/events/${e.slug}`}
            style={{
              scrollSnapAlign: "start",
              flex: "0 0 auto",
              width: 260,
              borderRadius: 16,
              overflow: "hidden",
              border: "1px solid var(--line-strong)",
              textDecoration: "none",
              background: "var(--obsidian-3)",
            }}
          >
            <div
              style={{
                position: "relative",
                height: 150,
                background: e.hero_url
                  ? `linear-gradient(180deg, rgba(10,10,15,0.1), rgba(10,10,15,0.5)), url(${e.hero_url}) center/cover`
                  : "linear-gradient(135deg, var(--obsidian-3), var(--volt))",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 10,
                  left: 10,
                  background: "var(--volt)",
                  color: "var(--obsidian-3)",
                  fontWeight: 700,
                  fontSize: 12,
                  padding: "4px 10px",
                  borderRadius: "var(--radius-full)",
                }}
              >
                {dateBadge(e.starts_at)}
              </span>
            </div>
            <div style={{ padding: "12px 14px 16px" }}>
              <div
                style={{
                  fontWeight: 700,
                  fontSize: 15,
                  color: "var(--arctic)",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {e.title}
              </div>
              <div style={{ color: "var(--fg3)", fontSize: 13, marginTop: 4 }}>{e.venue_name}</div>
              {e.dates_count > 1 && e.price_from != null ? (
                <div style={{ color: "var(--fg3)", fontSize: 12, marginTop: 6 }}>
                  {t("home.events.multi", {
                    n: e.dates_count,
                    price: Math.round(e.price_from),
                  })}
                </div>
              ) : null}
              <div style={{ color: "var(--volt)", fontSize: 13, fontWeight: 600, marginTop: 8 }}>
                {t("home.events.cta")} →
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
