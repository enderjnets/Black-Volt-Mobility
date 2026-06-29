"use client";

import { useEffect, useState } from "react";

import ReviewForm from "@/components/bv/web/ReviewForm";
import { useI18n } from "@/lib/i18n";
import { getReviewInvite } from "@/lib/reviews";

type State = "loading" | "error" | { author_name: string | null };

export default function InvitedReviewPage({ params }: { params: { token: string } }) {
  const { t } = useI18n();
  const [state, setState] = useState<State>("loading");

  useEffect(() => {
    let alive = true;
    getReviewInvite(params.token)
      .then((inv) => alive && setState({ author_name: inv.author_name }))
      .catch(() => alive && setState("error"));
    return () => {
      alive = false;
    };
  }, [params.token]);

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
      {state === "loading" ? null : state === "error" ? (
        <p style={{ fontSize: 15, color: "var(--fg2)" }}>{t("reviews.page.invalid")}</p>
      ) : (
        <ReviewForm token={params.token} defaultName={state.author_name ?? undefined} />
      )}
    </main>
  );
}
