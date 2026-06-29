"use client";

import { useState } from "react";

import StarRating from "@/components/bv/StarRating";
import { useI18n } from "@/lib/i18n";
import { submitReview } from "@/lib/reviews";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "11px 13px",
  fontSize: 15,
  color: "var(--arctic)",
  background: "var(--obsidian-3)",
  border: "1px solid var(--line)",
  borderRadius: "var(--radius-md)",
  outline: "none",
  fontFamily: "var(--font-sans)",
};

export default function ReviewForm({
  token,
  rideId,
  tenantSlug,
  defaultName,
}: {
  token?: string;
  rideId?: number;
  tenantSlug?: string;
  defaultName?: string;
}) {
  const { t } = useI18n();
  const [rating, setRating] = useState(5);
  const [body, setBody] = useState("");
  const [name, setName] = useState(defaultName ?? "");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [err, setErr] = useState("");

  async function submit() {
    if (body.trim().length < 3 || !name.trim()) {
      setErr(t("reviews.form.required"));
      return;
    }
    setState("sending");
    setErr("");
    try {
      await submitReview({
        rating,
        body: body.trim(),
        author_name: name.trim(),
        author_email: email.trim() || undefined,
        token,
        ride_id: rideId,
        tenant_slug: tenantSlug,
      });
      setState("done");
    } catch {
      setState("error");
      setErr(t("reviews.form.error"));
    }
  }

  if (state === "done") {
    return (
      <div
        style={{
          padding: 24,
          textAlign: "center",
          background: "var(--obsidian-2)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius-lg)",
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 8 }}>★</div>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px", color: "var(--arctic)" }}>
          {t("reviews.form.thanksTitle")}
        </h2>
        <p style={{ fontSize: 15, lineHeight: 1.6, color: "var(--fg2)", margin: 0 }}>
          {t("reviews.form.thanks")}
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <label style={{ display: "block", fontSize: 13, color: "var(--fg2)", marginBottom: 8 }}>
          {t("reviews.form.rating")}
        </label>
        <StarRating value={rating} onChange={setRating} size={32} />
      </div>

      <div>
        <label style={{ display: "block", fontSize: 13, color: "var(--fg2)", marginBottom: 6 }}>
          {t("reviews.form.review")}
        </label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          maxLength={1500}
          rows={5}
          placeholder={t("reviews.form.reviewPlaceholder")}
          style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }}
        />
      </div>

      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
        <div>
          <label style={{ display: "block", fontSize: 13, color: "var(--fg2)", marginBottom: 6 }}>
            {t("reviews.form.name")}
          </label>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} style={inputStyle} />
        </div>
        <div>
          <label style={{ display: "block", fontSize: 13, color: "var(--fg2)", marginBottom: 6 }}>
            {t("reviews.form.email")}
          </label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            maxLength={254}
            style={inputStyle}
          />
        </div>
      </div>

      {err && <p style={{ color: "#ff6b6b", fontSize: 13.5, margin: 0 }}>{err}</p>}

      <button
        type="button"
        onClick={submit}
        disabled={state === "sending"}
        style={{
          background: "var(--volt)",
          color: "#0A0A0F",
          fontWeight: 700,
          fontSize: 15,
          border: "none",
          padding: "13px 26px",
          borderRadius: "var(--radius-md)",
          cursor: state === "sending" ? "default" : "pointer",
          opacity: state === "sending" ? 0.6 : 1,
          boxShadow: "var(--shadow-volt)",
          justifySelf: "start",
        }}
      >
        {state === "sending" ? t("reviews.form.sending") : t("reviews.form.submit")}
      </button>

      <p style={{ fontSize: 12, color: "var(--fg3)", margin: 0 }}>{t("reviews.form.moderationNote")}</p>
    </div>
  );
}
