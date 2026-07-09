"use client";

import Link from "next/link";

import { useI18n } from "@/lib/i18n";

type Variant = "badge" | "primary" | "sticky";

// Bilingual (EN/ES) price + CTA for the event landing. The landing itself is a server
// component and the chosen language lives only in localStorage (no cookie), so any copy
// that must localize has to render on the client — hence this small wrapper. Leads with the
// reservation deposit (1/3 of the round-trip estimate) instead of the full total, which is
// where paid mobile traffic was bouncing.
export default function EventCta({
  variant,
  deposit,
  total,
  href,
}: {
  variant: Variant;
  deposit: number;
  total?: number;
  href?: string;
}) {
  const { t } = useI18n();
  const totalVal = total ?? deposit;

  if (variant === "badge") {
    return (
      <div
        style={{
          display: "inline-block",
          background: "var(--volt)",
          color: "var(--obsidian-3)",
          fontWeight: 700,
          fontSize: 13,
          padding: "6px 12px",
          borderRadius: "var(--radius-full)",
          marginBottom: 14,
        }}
      >
        {t("event.badge", { deposit, total: totalVal })}
      </div>
    );
  }

  if (variant === "sticky") {
    return (
      <Link href={href ?? "#"} className="bv-event-sticky-cta">
        {t("event.sticky", { deposit })}
      </Link>
    );
  }

  // primary — a full CTA button with a supporting breakdown line beneath it
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <Link
        href={href ?? "#"}
        style={{
          display: "inline-block",
          padding: "13px 26px",
          borderRadius: "var(--radius-full)",
          fontWeight: 700,
          fontSize: 15,
          textDecoration: "none",
          background: "var(--volt)",
          color: "var(--obsidian-3)",
          border: "none",
          textAlign: "center",
        }}
      >
        {t("event.cta.reserve", { deposit })}
      </Link>
      <span style={{ fontSize: 13, opacity: 0.8 }}>{t("event.cta.sub", { total: totalVal })}</span>
    </div>
  );
}
