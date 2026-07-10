"use client";

import Link from "next/link";

import { useI18n } from "@/lib/i18n";

type DateOption = {
  slug: string;
  startsAt: string; // ISO
  price: number; // round-trip total for this date
  href: string; // prebuilt server-side: canonical page + ?date=… + preserved UTMs
};

// Date picker for a multi-date show. The landing is a server component and re-fetches per request,
// so selection is navigation-based: each pill is a <Link> to the canonical page with ?date= set,
// and the server swaps the price/booking surfaces to that night. Only the day-of-week/date labels
// localize (language lives in localStorage, not a cookie), so this renders on the client.
export default function EventDateSelector({
  dates,
  selectedSlug,
}: {
  dates: DateOption[];
  selectedSlug: string;
}) {
  const { t, lang } = useI18n();
  const locale = lang === "es" ? "es" : "en-US";

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, opacity: 0.75, marginBottom: 10 }}>
        {t("event.dates.title")}
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {dates.map((d) => {
          const active = d.slug === selectedSlug;
          const when = new Date(d.startsAt).toLocaleDateString(locale, {
            weekday: "short",
            month: "short",
            day: "numeric",
            timeZone: "America/Denver",
          });
          return (
            <Link
              key={d.slug}
              href={d.href}
              scroll={false}
              aria-current={active ? "true" : undefined}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 2,
                minWidth: 92,
                padding: "10px 16px",
                borderRadius: 14,
                textDecoration: "none",
                border: active ? "1px solid var(--volt)" : "1px solid rgba(255,255,255,0.16)",
                background: active ? "var(--volt)" : "rgba(255,255,255,0.04)",
                color: active ? "var(--obsidian-3)" : "var(--silver, #e8e8ea)",
                fontWeight: 700,
              }}
            >
              <span style={{ fontSize: 13, letterSpacing: 0.2 }}>{when}</span>
              <span style={{ fontSize: 13, opacity: active ? 0.85 : 0.7 }}>${d.price}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
