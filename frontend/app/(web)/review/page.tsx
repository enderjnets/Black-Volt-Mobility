"use client";

import { Suspense } from "react";

import { useSearchParams } from "next/navigation";

import ReviewForm from "@/components/bv/web/ReviewForm";
import { useI18n } from "@/lib/i18n";

function ReviewFormWithRide() {
  const sp = useSearchParams();
  const raw = sp.get("ride");
  const rideId = raw && Number.isFinite(Number(raw)) ? Number(raw) : undefined;
  const driver = sp.get("driver") || undefined;
  return <ReviewForm rideId={rideId} tenantSlug={driver} />;
}

export default function ReviewPage() {
  const { t } = useI18n();
  return (
    <main style={{ maxWidth: 620, margin: "0 auto", padding: "28px 18px 64px" }}>
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 28,
          fontWeight: 700,
          margin: "0 0 8px",
          color: "var(--arctic)",
        }}
      >
        {t("reviews.page.title")}
      </h1>
      <p style={{ fontSize: 15, lineHeight: 1.6, color: "var(--fg2)", margin: "0 0 24px" }}>
        {t("reviews.page.subtitle")}
      </p>
      <Suspense fallback={null}>
        <ReviewFormWithRide />
      </Suspense>
    </main>
  );
}
