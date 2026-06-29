"use client";

import { useCallback, useEffect, useState } from "react";

import StarRating from "../StarRating";
import { Button, Card, Field, Pill, Toggle } from "../ui";
import { fetchMe } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import {
  type AdminReview,
  type InviteResult,
  type ReviewCandidate,
  createReviewInvite,
  deleteReview,
  listAdminReviews,
  listReviewCandidates,
  patchReview,
} from "@/lib/reviews";

type Tone = "warning" | "success" | "muted";
const STATUS_TONE: Record<string, Tone> = {
  pending: "warning",
  approved: "success",
  rejected: "muted",
};

export function Reviews() {
  const { t, lang } = useI18n();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [rows, setRows] = useState<AdminReview[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [tenantFilter, setTenantFilter] = useState<number | "all">("all");
  const [drivers, setDrivers] = useState<{ id: number; name: string }[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Admin-only when auth is enabled; in open mode (auth off) the single owner is the user.
    // The backend enforces require_admin in production regardless.
    fetchMe()
      .then((m) => setIsAdmin(!!m.is_admin || !m.auth_enabled))
      .catch(() => setIsAdmin(false));
  }, []);

  const load = useCallback(async () => {
    setRows(
      await listAdminReviews(filter || undefined, tenantFilter === "all" ? undefined : tenantFilter),
    );
  }, [filter, tenantFilter]);

  useEffect(() => {
    if (isAdmin) load().catch(() => setRows([]));
  }, [isAdmin, load]);

  // Build the driver list from the full set so the dropdown survives filtering.
  useEffect(() => {
    if (!isAdmin) return;
    listAdminReviews()
      .then((rs) => {
        const seen = new Map<number, string>();
        for (const r of rs) {
          if (!seen.has(r.tenant_id)) seen.set(r.tenant_id, r.tenant_name || `#${r.tenant_id}`);
        }
        setDrivers([...seen].map(([id, name]) => ({ id, name })));
      })
      .catch(() => setDrivers([]));
  }, [isAdmin]);

  async function mutate(id: number, patch: Parameters<typeof patchReview>[1]) {
    setBusy(true);
    try {
      const updated = await patchReview(id, patch);
      setRows((rs) => rs.map((r) => (r.id === id ? updated : r)));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setBusy(true);
    try {
      await deleteReview(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
    } finally {
      setBusy(false);
    }
  }

  if (isAdmin === false) {
    return (
      <Card pad={20}>
        <p style={{ color: "var(--fg2)", margin: 0 }}>
          {lang === "es"
            ? "No tienes acceso a esta sección."
            : "You don’t have access to this section."}
        </p>
      </Card>
    );
  }

  const FILTERS: { key: string; label: string }[] = [
    { key: "", label: t("dash.reviews.filter.all") },
    { key: "pending", label: t("dash.reviews.filter.pending") },
    { key: "approved", label: t("dash.reviews.filter.approved") },
    { key: "rejected", label: t("dash.reviews.filter.rejected") },
  ];

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: "0 0 6px", color: "var(--arctic)" }}>
          {t("dash.reviews.title")}
        </h1>
        <p style={{ fontSize: 14, color: "var(--fg2)", margin: 0, maxWidth: 640 }}>
          {t("dash.reviews.subtitle")}
        </p>
      </div>

      <RequestPanel lang={lang} t={t} onSent={load} />

      {drivers.length > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--fg2)" }}>{t("dash.reviews.driver")}</span>
          <select
            value={tenantFilter === "all" ? "all" : String(tenantFilter)}
            onChange={(e) =>
              setTenantFilter(e.target.value === "all" ? "all" : Number(e.target.value))
            }
            style={{
              padding: "6px 12px",
              fontSize: 13,
              color: "var(--arctic)",
              background: "var(--obsidian-3)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-full)",
            }}
          >
            <option value="all">{t("dash.reviews.filter.allDrivers")}</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {FILTERS.map((f) => (
          <button
            key={f.key || "all"}
            onClick={() => setFilter(f.key)}
            style={{
              fontSize: 13,
              fontWeight: 600,
              padding: "6px 14px",
              borderRadius: "var(--radius-full)",
              cursor: "pointer",
              color: filter === f.key ? "#0A0A0F" : "var(--silver)",
              background: filter === f.key ? "var(--volt)" : "var(--obsidian-3)",
              border: "1px solid var(--line)",
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <Card pad={20}>
          <p style={{ color: "var(--fg3)", margin: 0, fontSize: 14 }}>{t("dash.reviews.empty")}</p>
        </Card>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {rows.map((r) => (
            <Card key={r.id} pad={16}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                <StarRating value={r.rating} readOnly size={16} />
                <strong style={{ fontSize: 14, color: "var(--arctic)" }}>{r.author_name}</strong>
                <Pill tone={STATUS_TONE[r.status]}>{t(`dash.reviews.status.${r.status}`)}</Pill>
                {r.verified && (
                  <Pill tone="muted" icon="check">
                    {t("dash.reviews.verifiedTag")}
                  </Pill>
                )}
                {r.tenant_name && (
                  <Pill tone="muted" icon="user">
                    {r.tenant_name}
                  </Pill>
                )}
              </div>

              <p style={{ fontSize: 14.5, lineHeight: 1.55, color: "var(--fg1)", margin: "10px 0" }}>
                “{r.body}”
              </p>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 16,
                  alignItems: "center",
                  paddingTop: 10,
                  borderTop: "1px solid var(--line)",
                }}
              >
                {r.status !== "approved" ? (
                  <Button size="sm" variant="solid" icon="check" disabled={busy} onClick={() => mutate(r.id, { status: "approved" })}>
                    {t("dash.reviews.approve")}
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" icon="x" disabled={busy} onClick={() => mutate(r.id, { status: "rejected" })}>
                    {t("dash.reviews.reject")}
                  </Button>
                )}

                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--fg2)" }}>
                  <Toggle on={r.show_on_home} setOn={(v) => mutate(r.id, { show_on_home: v })} />
                  {t("dash.reviews.showHome")}
                </label>

                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--fg2)" }}>
                  <Toggle on={r.featured} setOn={(v) => mutate(r.id, { featured: v })} />
                  {t("dash.reviews.featured")}
                </label>

                <span style={{ marginLeft: "auto" }}>
                  <Button size="sm" variant="ghost" icon="trash-2" disabled={busy} onClick={() => remove(r.id)}>
                    {t("dash.reviews.delete")}
                  </Button>
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function RequestPanel({
  t,
  lang,
  onSent,
}: {
  t: (k: string) => string;
  lang: string;
  onSent: () => void;
}) {
  const [cands, setCands] = useState<ReviewCandidate[]>([]);
  const [rideId, setRideId] = useState<number | undefined>();
  const [name, setName] = useState("");
  const [emailAddr, setEmailAddr] = useState("");
  const [phone, setPhone] = useState("");
  const [emailNow, setEmailNow] = useState(true);
  const [result, setResult] = useState<InviteResult | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listReviewCandidates().then(setCands).catch(() => setCands([]));
  }, []);

  function pick(id: string) {
    const c = cands.find((x) => String(x.ride_id) === id);
    setRideId(c?.ride_id);
    setName(c?.name ?? "");
    setEmailAddr(c?.email ?? "");
    setPhone(c?.phone ?? "");
    setResult(null);
    setNote("");
  }

  async function create(channels: string[]) {
    setBusy(true);
    setNote("");
    try {
      const res = await createReviewInvite({
        ride_id: rideId,
        to_email: emailAddr || undefined,
        to_phone: phone || undefined,
        author_name: name || undefined,
        channels,
        lang,
      });
      setResult(res);
      if (channels.includes("email")) {
        setNote(res.email_status === "skipped" || !emailAddr ? t("dash.reviews.request.emailskip") : t("dash.reviews.request.emailed"));
      }
      onSent();
      return res;
    } finally {
      setBusy(false);
    }
  }

  async function doText() {
    const res = result ?? (await create([]));
    if (res) window.location.href = res.sms_href;
  }

  async function doCopy() {
    const res = result ?? (await create([]));
    if (res) {
      try {
        await navigator.clipboard.writeText(res.message);
        setNote(t("dash.reviews.request.copied"));
      } catch {
        setNote(res.message);
      }
    }
  }

  return (
    <Card pad={18}>
      <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 12px", color: "var(--arctic)" }}>
        {t("dash.reviews.request.title")}
      </h2>

      <label style={{ display: "block", fontSize: 13, color: "var(--fg2)", marginBottom: 6 }}>
        {t("dash.reviews.request.pick")}
      </label>
      <select
        onChange={(e) => pick(e.target.value)}
        defaultValue=""
        style={{
          width: "100%",
          padding: "10px 12px",
          fontSize: 14,
          color: "var(--arctic)",
          background: "var(--obsidian-3)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius-md)",
          marginBottom: 12,
        }}
      >
        <option value="" disabled>
          {cands.length === 0 ? t("dash.reviews.request.none") : "—"}
        </option>
        {cands.map((c) => (
          <option key={c.ride_id} value={c.ride_id}>
            {c.name} · {c.route}
          </option>
        ))}
      </select>

      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <Field label={t("reviews.form.name")} value={name} onChange={setName} />
        <Field label={t("reviews.form.email")} value={emailAddr} onChange={setEmailAddr} />
        <Field label="Phone" value={phone} onChange={setPhone} />
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--fg2)", margin: "12px 0" }}>
        <Toggle on={emailNow} setOn={setEmailNow} />
        {t("dash.reviews.request.email_btn")}
      </label>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        <Button variant="solid" size="sm" icon="mail" disabled={busy} onClick={() => create(emailNow ? ["email"] : [])}>
          {t("dash.reviews.request.title")}
        </Button>
        <Button variant="tint" size="sm" icon="message-circle" disabled={busy} onClick={doText}>
          {t("dash.reviews.request.sms_btn")}
        </Button>
        <Button variant="ghost" size="sm" icon="copy" disabled={busy} onClick={doCopy}>
          {t("dash.reviews.request.copy_btn")}
        </Button>
      </div>

      {note && <p style={{ fontSize: 13, color: "var(--volt)", margin: "10px 0 0" }}>{note}</p>}
      {result && (
        <p style={{ fontSize: 12.5, color: "var(--fg3)", margin: "8px 0 0", wordBreak: "break-all" }}>
          {t("dash.reviews.request.link")}: {result.link}
        </p>
      )}
    </Card>
  );
}
