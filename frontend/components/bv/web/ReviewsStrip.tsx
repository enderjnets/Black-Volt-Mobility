"use client";

import { useEffect, useState } from "react";

import StarRating from "@/components/bv/StarRating";
import { useI18n } from "@/lib/i18n";
import { listPublicReviews, type PublicReview } from "@/lib/reviews";

/**
 * Client island that shows APPROVED reviews for a surface (home / route / profile).
 * Renders nothing until there are real reviews — never placeholders.
 */
export default function ReviewsStrip({
  surface = "home",
  tenantId,
  title,
  limit = 6,
}: {
  surface?: "home" | "route" | "profile";
  tenantId?: number;
  title?: string;
  limit?: number;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<PublicReview[] | null>(null);

  useEffect(() => {
    let alive = true;
    listPublicReviews({ surface, tenantId, limit })
      .then((r) => alive && setRows(r))
      .catch(() => alive && setRows([]));
    return () => {
      alive = false;
    };
  }, [surface, tenantId, limit]);

  if (!rows || rows.length === 0) return null;

  return (
    <section style={{ marginTop: 34 }}>
      <h2 style={{ fontSize: 19, fontWeight: 700, margin: "0 0 14px", color: "var(--arctic)" }}>
        {title ?? t("reviews.title")}
      </h2>
      <div
        style={{
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
        }}
      >
        {rows.map((r, i) => (
          <blockquote
            key={i}
            style={{
              margin: 0,
              padding: 16,
              background: "var(--obsidian-2)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-lg)",
            }}
          >
            <StarRating value={r.rating} readOnly size={16} />
            <p style={{ margin: "8px 0", fontSize: 15, lineHeight: 1.55, color: "var(--fg1)" }}>
              “{r.body}”
            </p>
            <cite style={{ fontSize: 13, color: "var(--fg3)", fontStyle: "normal" }}>
              — {r.author_name}
              {r.verified && (
                <span style={{ color: "var(--volt)", marginLeft: 6 }}>· {t("reviews.verified")}</span>
              )}
            </cite>
            {r.owner_reply && (
              <p
                style={{
                  margin: "10px 0 0",
                  paddingTop: 10,
                  borderTop: "1px solid var(--line)",
                  fontSize: 13.5,
                  color: "var(--fg2)",
                }}
              >
                <strong style={{ color: "var(--arctic)" }}>{t("reviews.ownerReply")}:</strong>{" "}
                {r.owner_reply}
              </p>
            )}
          </blockquote>
        ))}
      </div>
    </section>
  );
}
