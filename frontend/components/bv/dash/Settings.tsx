"use client";

/* Brand & account settings: edit the tenant's public profile + brand (persisted
   to the Tenant), upload a logo/hero photo, and view the read-only status of the
   Square payout + notification channels. Mirrors the Rates editor layout. */

import { type ChangeEvent, useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { InstallButton } from "../InstallButton";
import { PushOptIn } from "../PushOptIn";
import { Button, Field, Pill, Toggle } from "../ui";
import { ShareLink } from "./ShareLink";
import {
  type CalendarConnection,
  disconnectCalendar,
  getCalendarConnection,
  startCalendarConnect,
} from "@/lib/calendar";
import { useI18n } from "@/lib/i18n";
import {
  getTenantSettings,
  instagramHandle,
  updateTenantSettings,
  uploadTenantAsset,
  type TenantSettings,
} from "@/lib/tenant";

const ACCENTS = ["#00E5FF", "#2BD4A0", "#FFC24B", "#FF5C6E", "#8B5CF6"];

type Form = {
  name: string;
  tagline: string;
  bio: string;
  instagram: string;
  website: string;
  vehicle: string;
  city: string;
  phone: string;
  brand_color: string;
  rating: string;
  since_year: string;
  review_reminders_enabled: boolean;
  review_reminder_hours: string;
  social_daily_media: "video" | "image" | "mixed";
};

function toForm(d: TenantSettings): Form {
  return {
    name: d.name || "",
    tagline: d.tagline || "",
    bio: d.bio || "",
    instagram: d.instagram || "",
    website: d.website || "",
    vehicle: d.vehicle || "",
    city: d.city || "",
    phone: d.phone || "",
    brand_color: d.brand_color || "#00E5FF",
    rating: d.rating != null ? String(d.rating) : "",
    since_year: d.since_year != null ? String(d.since_year) : "",
    review_reminders_enabled: d.review_reminders_enabled ?? true,
    review_reminder_hours: d.review_reminder_hours != null ? String(d.review_reminder_hours) : "3",
    social_daily_media: d.social_daily_media ?? "video",
  };
}

export function Settings() {
  const { t } = useI18n();
  const [data, setData] = useState<TenantSettings | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [loadErr, setLoadErr] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [upBusy, setUpBusy] = useState<"logo" | "photo" | null>(null);
  const [upErr, setUpErr] = useState<string | null>(null);
  const logoRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<HTMLInputElement>(null);

  const load = () =>
    getTenantSettings()
      .then((d) => {
        setData(d);
        setForm(toForm(d));
        setLoadErr(false);
      })
      .catch(() => setLoadErr(true));
  useEffect(() => {
    load();
  }, []);

  const set = (k: keyof Form, v: string) => setForm((f) => (f ? { ...f, [k]: v } : f));
  const dirty = !!data && !!form && JSON.stringify(form) !== JSON.stringify(toForm(data));

  const save = async () => {
    if (!form || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const ratingNum = form.rating.trim() === "" ? null : Number(form.rating);
      const yearNum = form.since_year.trim() === "" ? null : Number(form.since_year);
      const hoursNum = Math.min(72, Math.max(1, Number(form.review_reminder_hours) || 3));
      const d = await updateTenantSettings({
        name: form.name.trim(),
        tagline: form.tagline.trim() || null,
        bio: form.bio.trim() || null,
        instagram: instagramHandle(form.instagram),
        website: form.website.trim() || null,
        vehicle: form.vehicle.trim() || null,
        city: form.city.trim() || null,
        phone: form.phone.trim() || null,
        brand_color: form.brand_color || null,
        rating: ratingNum != null && !Number.isNaN(ratingNum) ? ratingNum : null,
        since_year: yearNum != null && !Number.isNaN(yearNum) ? yearNum : null,
        review_reminders_enabled: form.review_reminders_enabled,
        review_reminder_hours: hoursNum,
        social_daily_media: form.social_daily_media,
      });
      setData(d);
      setForm(toForm(d));
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setErr(e instanceof Error && e.message ? e.message : "save");
    } finally {
      setBusy(false);
    }
  };

  const onPick = (kind: "logo" | "photo") => async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!file) return;
    setUpBusy(kind);
    setUpErr(null);
    try {
      const d = await uploadTenantAsset(kind, file);
      setData(d);
    } catch (er) {
      setUpErr(er instanceof Error && er.message ? er.message : "upload");
    } finally {
      setUpBusy(null);
    }
  };

  if (loadErr) {
    return (
      <div style={{ padding: 28, color: "var(--danger)", fontSize: 14 }}>
        {t("dash.settings.loadErr")}
      </div>
    );
  }
  if (!data || !form) {
    return (
      <div style={{ padding: 28, color: "var(--fg3)", fontSize: 14 }}>{t("common.loading")}</div>
    );
  }

  const pay = data.payments;

  return (
    <div
      className="bv-dash-grid"
      style={{ padding: 28, display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 22, alignItems: "start" }}
    >
      {/* ── Left: editable profile + brand ─────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <Section title={t("dash.settings.profileSection")} icon="user">
          <Field icon="zap" label={t("dash.settings.name")} value={form.name} onChange={(v) => set("name", v)} />
          <Field icon="sparkles" label={t("dash.settings.tagline")} value={form.tagline} onChange={(v) => set("tagline", v)} />
          <TextArea label={t("dash.settings.bio")} hint={t("dash.settings.bioHint")} value={form.bio} onChange={(v) => set("bio", v)} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field icon="instagram" label={t("dash.settings.instagram")} value={form.instagram} onChange={(v) => set("instagram", v)} placeholder="@blackvolt" />
            <Field icon="globe" label={t("dash.settings.website")} value={form.website} onChange={(v) => set("website", v)} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field icon="car" label={t("dash.settings.vehicle")} value={form.vehicle} onChange={(v) => set("vehicle", v)} />
            <Field icon="map-pin" label={t("dash.settings.city")} value={form.city} onChange={(v) => set("city", v)} />
          </div>
          <Field icon="phone" type="tel" label={t("dash.settings.phone")} hint={t("dash.settings.phoneHint")} value={form.phone} onChange={(v) => set("phone", v)} placeholder="+1 303 555 1234" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field icon="star" type="number" label={t("dash.settings.rating")} value={form.rating} onChange={(v) => set("rating", v)} placeholder="4.98" />
            <Field icon="clock" type="number" label={t("dash.settings.sinceYear")} value={form.since_year} onChange={(v) => set("since_year", v)} placeholder="2021" />
          </div>
        </Section>

        <Section title={t("push.title")} icon="bell">
          <PushOptIn />
          <div style={{ marginTop: 12, fontSize: 13, color: "var(--volt)" }}>
            <InstallButton />
          </div>
        </Section>

        <Section title={t("dash.settings.reviewsSection")} icon="star">
          <label
            style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--arctic)" }}
          >
            <Toggle
              on={form.review_reminders_enabled}
              setOn={(v) => setForm((f) => (f ? { ...f, review_reminders_enabled: v } : f))}
            />
            {t("dash.settings.reviewReminders")}
          </label>
          <p style={{ fontSize: 13, color: "var(--silver)", margin: "8px 0 0", lineHeight: 1.5 }}>
            {t("dash.settings.reviewRemindersHint")}
          </p>
          {form.review_reminders_enabled && (
            <div style={{ marginTop: 12, maxWidth: 240 }}>
              <Field
                icon="clock"
                type="number"
                label={t("dash.settings.reviewHours")}
                value={form.review_reminder_hours}
                onChange={(v) => set("review_reminder_hours", v)}
              />
            </div>
          )}
        </Section>

        <Section title={t("dash.settings.socialSection")} icon="sparkles">
          <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>
            {t("dash.settings.dailyMedia")}
          </div>
          <div
            style={{
              display: "flex",
              gap: 4,
              background: "var(--obsidian-3)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-full)",
              padding: 4,
              width: "fit-content",
            }}
          >
            {(["video", "image", "mixed"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setForm((f) => (f ? { ...f, social_daily_media: k } : f))}
                style={{
                  padding: "6px 15px",
                  borderRadius: "var(--radius-full)",
                  cursor: "pointer",
                  fontSize: 12.5,
                  fontWeight: 600,
                  border: "none",
                  background:
                    form.social_daily_media === k ? "var(--volt-bg-20)" : "transparent",
                  color: form.social_daily_media === k ? "var(--volt)" : "var(--silver)",
                  boxShadow:
                    form.social_daily_media === k ? "inset 0 0 0 1px var(--volt-border)" : "none",
                }}
              >
                {t(`dash.settings.dailyMedia.${k}`)}
              </button>
            ))}
          </div>
          <p style={{ fontSize: 13, color: "var(--silver)", margin: "8px 0 0", lineHeight: 1.5 }}>
            {t("dash.settings.dailyMediaHint")}
          </p>
        </Section>

        <Section title={t("dash.settings.brandSection")} icon="wand">
          <div>
            <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>{t("dash.settings.accent")}</div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              {ACCENTS.map((c) => (
                <button
                  key={c}
                  aria-label={c}
                  onClick={() => set("brand_color", c)}
                  style={{
                    width: 34,
                    height: 34,
                    borderRadius: 8,
                    background: c,
                    cursor: "pointer",
                    border: "none",
                    boxShadow:
                      form.brand_color.toUpperCase() === c
                        ? "0 0 0 2px var(--void), 0 0 0 4px var(--volt)"
                        : "none",
                  }}
                />
              ))}
              <label
                style={{
                  position: "relative",
                  width: 34,
                  height: 34,
                  borderRadius: 8,
                  border: "1px dashed var(--line-strong)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  overflow: "hidden",
                  background: ACCENTS.includes(form.brand_color.toUpperCase())
                    ? "var(--obsidian-3)"
                    : form.brand_color,
                }}
              >
                <Icon name="plus" size={15} color="var(--silver)" />
                <input
                  type="color"
                  value={form.brand_color}
                  onChange={(e) => set("brand_color", e.target.value.toUpperCase())}
                  style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer" }}
                />
              </label>
            </div>
            <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 10 }}>{t("dash.settings.accentHint")}</div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 4 }}>
            <Uploader
              label={t("dash.settings.logo")}
              url={data.logo_url}
              round
              busy={upBusy === "logo"}
              onClick={() => logoRef.current?.click()}
              t={t}
            />
            <Uploader
              label={t("dash.settings.photo")}
              url={data.photo_url}
              busy={upBusy === "photo"}
              onClick={() => photoRef.current?.click()}
              t={t}
            />
          </div>
          <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.settings.uploadHint")}</div>
          {upErr && (
            <div style={{ fontSize: 12.5, color: "var(--danger)", display: "flex", gap: 6, alignItems: "center" }}>
              <Icon name="alert-circle" size={14} color="var(--danger)" />
              <span>{t("dash.settings.uploadErr")}</span>
            </div>
          )}
          <input ref={logoRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={onPick("logo")} style={{ display: "none" }} />
          <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={onPick("photo")} style={{ display: "none" }} />
        </Section>
      </div>

      {/* ── Right: actions + integration status ────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 18, boxShadow: "var(--shadow-volt)" }}>
          {err && (
            <div style={{ fontSize: 12.5, color: "var(--danger)", marginBottom: 12, display: "flex", gap: 6, alignItems: "flex-start" }}>
              <Icon name="alert-circle" size={14} color="var(--danger)" />
              <span>{err === "save" ? t("dash.settings.saveErr") : err}</span>
            </div>
          )}
          <Button variant="solid" full size="lg" icon={saved ? "check" : "zap"} disabled={busy || !form} onClick={save}>
            {busy ? t("dash.settings.saving") : saved ? t("dash.settings.saved") : t("dash.settings.save")}
          </Button>
          {dirty && !busy && !saved && (
            <div style={{ marginTop: 10, display: "flex", justifyContent: "center" }}>
              <Pill tone="volt" icon="circle-dot">{t("dash.settings.unsaved")}</Pill>
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            <Button variant="ghost" full icon="external-link" onClick={() => window.open(`/d/${data.slug}`, "_blank")}>
              {t("dash.settings.viewPublic")}
            </Button>
          </div>
        </div>

        <ShareLink slug={data.slug} />

        <StatusCard title={t("dash.settings.paymentsSection")} icon="credit-card">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <Pill tone={pay.connected ? "success" : "muted"} icon={pay.connected ? "check" : "circle-dot"}>
              {pay.connected ? t("dash.settings.paymentsConnected") : t("dash.settings.paymentsNotConnected")}
            </Pill>
            <Pill tone={pay.live ? "volt" : "warning"}>
              {pay.live ? t("dash.settings.paymentsLive") : t("dash.settings.paymentsSandbox")}
            </Pill>
          </div>
          <p style={{ fontSize: 13, color: "var(--silver)", margin: 0, lineHeight: 1.5 }}>{t("dash.settings.paymentsBody")}</p>
        </StatusCard>

        <GoogleCalendarCard />

        <StatusCard title={t("dash.settings.notifSection")} icon="message-circle">
          <p style={{ fontSize: 13, color: "var(--silver)", margin: 0, lineHeight: 1.5 }}>{t("dash.settings.notifSoon")}</p>
        </StatusCard>
      </div>
    </div>
  );
}

function GoogleCalendarCard() {
  const { t } = useI18n();
  const [conn, setConn] = useState<CalendarConnection | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Surface the ?calendar=connected|error flag the OAuth callback redirects with.
  const [flag, setFlag] = useState<string | null>(null);

  useEffect(() => {
    getCalendarConnection().then(setConn).catch(() => setConn(null));
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search).get("calendar");
      if (p) {
        setFlag(p);
        // Clean the URL so a refresh doesn't re-show the banner.
        const url = new URL(window.location.href);
        url.searchParams.delete("calendar");
        window.history.replaceState({}, "", url.toString());
      }
    }
  }, []);

  const connect = async () => {
    setBusy(true);
    setErr(null);
    try {
      await startCalendarConnect(); // full-page redirect to Google
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setErr(null);
    try {
      await disconnectCalendar();
      setConn(await getCalendarConnection());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  };

  const body = (text: string) => (
    <p style={{ fontSize: 13, color: "var(--silver)", margin: 0, lineHeight: 1.5 }}>{text}</p>
  );

  return (
    <StatusCard title={t("dash.calendar.title")} icon="external-link">
      {flag === "connected" && (
        <div style={{ marginBottom: 10 }}>
          <Pill tone="success" icon="circle-check">
            {t("dash.calendar.justConnected")}
          </Pill>
        </div>
      )}
      {flag === "error" && (
        <div style={{ marginBottom: 10 }}>
          <Pill tone="warning" icon="alert-circle">
            {t("dash.calendar.connectError")}
          </Pill>
        </div>
      )}

      {conn?.is_admin ? (
        <>
          <div style={{ marginBottom: 10 }}>
            <Pill tone="volt" icon="shield-check">
              {t("dash.calendar.adminShared")}
            </Pill>
          </div>
          {body(t("dash.calendar.adminBody"))}
        </>
      ) : !conn?.oauth_configured ? (
        <>
          <div style={{ marginBottom: 10 }}>
            <Pill tone="muted" icon="circle-dot">
              {t("dash.calendar.unavailable")}
            </Pill>
          </div>
          {body(t("dash.calendar.unavailableBody"))}
        </>
      ) : conn?.connected ? (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <Pill tone="success" icon="circle-check">
              {t("dash.calendar.connected")}
            </Pill>
            {conn.google_email && (
              <Pill tone="muted">
                {conn.google_email}
              </Pill>
            )}
          </div>
          {body(t("dash.calendar.connectedBody"))}
          <div style={{ marginTop: 12 }}>
            <Button variant="ghost" size="sm" onClick={disconnect} disabled={busy}>
              {t("dash.calendar.disconnect")}
            </Button>
          </div>
        </>
      ) : (
        <>
          <div style={{ marginBottom: 10 }}>
            <Pill tone="muted" icon="circle-dot">
              {t("dash.calendar.notConnected")}
            </Pill>
          </div>
          {body(t("dash.calendar.body"))}
          <div style={{ marginTop: 12 }}>
            <Button variant="solid" size="sm" icon="external-link" onClick={connect} disabled={busy}>
              {t("dash.calendar.connect")}
            </Button>
          </div>
        </>
      )}
      {err && (
        <p style={{ fontSize: 12, color: "var(--danger, #FF5C6E)", marginTop: 8 }}>{err}</p>
      )}
    </StatusCard>
  );
}

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: "18px 20px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <Icon name={icon} size={16} color="var(--volt)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{title}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>{children}</div>
    </div>
  );
}

function StatusCard({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <Icon name={icon} size={15} color="var(--silver)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 14, color: "var(--arctic)" }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function TextArea({ label, hint, value, onChange }: { label: string; hint?: string; value: string; onChange: (v: string) => void }) {
  return (
    <label style={{ display: "block" }}>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{label}</div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        maxLength={2000}
        style={{
          width: "100%",
          resize: "vertical",
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: "12px 14px",
          color: "var(--arctic)",
          fontSize: 14,
          fontFamily: "var(--font-sans)",
          outline: "none",
        }}
      />
      {hint && <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 6 }}>{hint}</div>}
    </label>
  );
}

function Uploader({
  label,
  url,
  round,
  busy,
  onClick,
  t,
}: {
  label: string;
  url: string | null;
  round?: boolean;
  busy: boolean;
  onClick: () => void;
  t: (k: string) => string;
}) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{label}</div>
      <button
        onClick={onClick}
        disabled={busy}
        style={{
          width: "100%",
          height: round ? 96 : 96,
          borderRadius: round ? "var(--radius-md)" : "var(--radius-md)",
          border: "1px solid var(--line-strong)",
          background: "var(--obsidian-3)",
          cursor: busy ? "wait" : "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          position: "relative",
          padding: 0,
        }}
      >
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={label} style={{ width: "100%", height: "100%", objectFit: round ? "contain" : "cover" }} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, color: "var(--silver)" }}>
            <Icon name="upload" size={20} color="var(--silver)" />
            <span style={{ fontSize: 12 }}>{t("dash.settings.upload")}</span>
          </div>
        )}
        {(busy || url) && (
          <span
            style={{
              position: "absolute",
              bottom: 6,
              right: 6,
              fontSize: 11,
              fontWeight: 600,
              color: "var(--void)",
              background: "var(--volt)",
              borderRadius: "var(--radius-full)",
              padding: "3px 9px",
            }}
          >
            {busy ? t("dash.settings.uploading") : t("dash.settings.change")}
          </span>
        )}
      </button>
    </div>
  );
}
