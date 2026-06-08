"use client";

/* Client detail drawer (CRM): profile + stats + ride history, with inline edit
   of the client's info and quick actions. Mirrors RideDetail's drawer shell. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { deleteClient, getClientDetail, updateClient, type ClientDetail as CD } from "@/lib/dashboard";
import type { RideRow } from "@/lib/booking";
import { StatusPill } from "./DashShell";
import { fmtWhen, uiStatus } from "./status";
import { RideDetail } from "./RideDetail";

const TIER_TONE: Record<string, "volt" | "muted" | "success"> = {
  VIP: "volt",
  Regular: "muted",
  New: "success",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

type Form = { name: string; phone: string; email: string; lang: string; home: string };

export function ClientDetail({
  clientId,
  onClose,
  onChanged,
}: {
  clientId: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const [c, setC] = useState<CD | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [openRide, setOpenRide] = useState<number | null>(null);
  const [confirmDel, setConfirmDel] = useState(false);

  const load = () =>
    getClientDetail(clientId)
      .then((d) => {
        setC(d);
        setForm({ name: d.name || "", phone: d.phone || "", email: d.email || "", lang: d.lang || "EN", home: d.home_address || "" });
      })
      .catch(() => setErr("load"));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const dirty =
    !!c &&
    !!form &&
    (form.name !== (c.name || "") ||
      form.phone !== (c.phone || "") ||
      form.email !== (c.email || "") ||
      form.lang !== (c.lang || "EN") ||
      form.home !== (c.home_address || ""));

  const save = async () => {
    if (!form || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await updateClient(clientId, {
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        lang: form.lang,
        home_address: form.home.trim() || null,
      });
      await load();
      onChanged?.();
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setErr(e instanceof Error && e.message ? e.message : "save");
    } finally {
      setBusy(false);
    }
  };

  const del = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteClient(clientId);
      onChanged?.();
      onClose();
    } catch {
      setErr("delete");
      setBusy(false);
      setConfirmDel(false);
    }
  };

  const newRide = () => {
    const p = new URLSearchParams();
    if (c?.name) p.set("name", c.name);
    if (c?.phone) p.set("phone", c.phone);
    if (c?.lang) p.set("lang", c.lang);
    router.push(`/dashboard/add?${p.toString()}`);
  };

  const set = (k: keyof Form, v: string) => setForm((f) => (f ? { ...f, [k]: v } : f));

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: "fixed", inset: 0, zIndex: 70, background: "rgba(5,5,9,0.72)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}
      >
        <div
          onClick={(e) => e.stopPropagation()}
          style={{ width: "100%", maxWidth: 480, maxHeight: "88dvh", overflowY: "auto", background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-volt)", padding: 24, position: "relative" }}
        >
          <button onClick={onClose} aria-label="Close" style={{ position: "absolute", top: 16, right: 16, background: "none", border: "none", cursor: "pointer", padding: 4 }}>
            <Icon name="x" size={18} color="var(--silver)" />
          </button>

          {!c || !form ? (
            <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
              {err ? t("dash.client.loadErr") : t("common.loading")}
            </div>
          ) : (
            <>
              {/* Header */}
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
                <div style={{ width: 46, height: 46, borderRadius: "50%", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon name="user" size={20} color="var(--silver)" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 19, color: "var(--arctic)" }}>{c.name}</div>
                  <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.client.memberSince")} {fmtDate(c.created_at)}</div>
                </div>
                <Pill tone={TIER_TONE[c.tier]} icon={c.tier === "VIP" ? "star" : undefined}>{t(`dash.tier.${c.tier}`)}</Pill>
              </div>

              {/* Stats */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 18 }}>
                <Stat label={t("dash.client.totalRides")} value={String(c.rides_count)} />
                <Stat label={t("dash.client.lifetime")} value={`$${c.lifetime_spend.toLocaleString()}`} />
                <Stat label={t("dash.client.lastRide")} value={c.last_ride_at ? fmtWhen(c.last_ride_at) : "—"} />
                <Stat label={t("dash.client.language")} value={c.lang} />
              </div>

              {/* Editable profile */}
              <div style={{ fontSize: 11.5, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>{t("dash.client.profile")}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
                <EditField label={t("dash.client.name")} icon="user" value={form.name} onChange={(v) => set("name", v)} />
                <EditField label={t("dash.client.phone")} icon="phone" value={form.phone} onChange={(v) => set("phone", v)} />
                <EditField label={t("dash.client.email")} icon="message-circle" value={form.email} onChange={(v) => set("email", v)} />
                <EditField label={t("dash.client.home")} icon="home" value={form.home} onChange={(v) => set("home", v)} />
                <div>
                  <div style={{ fontSize: 11.5, color: "var(--fg3)", marginBottom: 5 }}>{t("dash.client.language")}</div>
                  <div style={{ display: "flex", gap: 4, background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: 4, width: "fit-content" }}>
                    {["EN", "ES"].map((v) => (
                      <button
                        key={v}
                        onClick={() => set("lang", v)}
                        style={{ padding: "6px 16px", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600, border: "none", fontFamily: "var(--font-sans)", background: form.lang === v ? "var(--volt-bg-20)" : "transparent", color: form.lang === v ? "var(--volt)" : "var(--silver)" }}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {err && err !== "load" && (
                <div style={{ fontSize: 12.5, color: "var(--danger)", marginBottom: 10, display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <Icon name="alert-circle" size={14} color="var(--danger)" />
                  <span>{err === "save" ? t("dash.client.saveErr") : err === "delete" ? t("dash.client.deleteErr") : err}</span>
                </div>
              )}

              <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                <Button variant={saved ? "ghost" : "solid"} icon={saved ? "check" : "circle-check"} disabled={!dirty || busy} onClick={save}>
                  {busy ? t("dash.client.saving") : saved ? t("dash.client.saved") : t("dash.client.save")}
                </Button>
                <Button variant="tint" icon="plus" disabled={busy} onClick={newRide}>{t("dash.client.newRideFor")}</Button>
              </div>

              {/* Ride history */}
              <div style={{ fontSize: 11.5, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>{t("dash.client.ridesHistory")}</div>
              {c.rides.length === 0 ? (
                <div style={{ fontSize: 13, color: "var(--fg3)", padding: "8px 0" }}>{t("dash.client.noRides")}</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {c.rides.map((r) => (
                    <RideHistoryRow key={r.id} r={r} onOpen={() => setOpenRide(r.id)} />
                  ))}
                </div>
              )}

              {/* Danger zone: delete keeps the ride history (rides are detached, the
                  passenger name/phone snapshot survives on each ride). */}
              <div style={{ marginTop: 22, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
                {confirmDel ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ fontSize: 12.5, color: "var(--silver)" }}>{t("dash.client.deleteConfirm")}</div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <Button variant="solid" icon="trash-2" disabled={busy} onClick={del} style={{ background: "var(--danger)", color: "var(--void)" }}>
                        {busy ? t("dash.client.deleting") : t("dash.client.deleteYes")}
                      </Button>
                      <Button variant="ghost" disabled={busy} onClick={() => setConfirmDel(false)}>
                        {t("dash.addClient.cancel")}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDel(true)}
                    style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--danger)", fontFamily: "var(--font-sans)" }}
                  >
                    <Icon name="trash-2" size={14} color="var(--danger)" />
                    {t("dash.client.delete")}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {openRide != null && (
        <RideDetail
          rideId={openRide}
          onClose={() => setOpenRide(null)}
          onChanged={() => {
            load();
            onChanged?.();
          }}
        />
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: "10px 12px" }}>
      <div style={{ fontSize: 11, color: "var(--fg3)" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--arctic)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
    </div>
  );
}

function EditField({ label, icon, value, onChange }: { label: string; icon: string; value: string; onChange: (v: string) => void }) {
  return (
    <label style={{ display: "block" }}>
      <div style={{ fontSize: 11.5, color: "var(--fg3)", marginBottom: 5 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--obsidian-3)", borderRadius: "var(--radius-md)", padding: "9px 11px", border: "1px solid var(--line-strong)" }}>
        <Icon name={icon} size={15} color="var(--silver)" />
        <input value={value} onChange={(e) => onChange(e.target.value)} style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", color: "var(--arctic)", fontSize: 13.5, fontFamily: "var(--font-sans)" }} />
      </div>
    </label>
  );
}

function RideHistoryRow({ r, onOpen }: { r: RideRow; onOpen: () => void }) {
  return (
    <div
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}
      style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", cursor: "pointer" }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: "var(--arctic)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {r.pickup} → {r.dropoff}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--fg3)", marginTop: 2 }}>{fmtWhen(r.scheduled_at)}</div>
      </div>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 14, color: "var(--volt)" }}>${Math.round(r.fare_total || 0)}</span>
      <StatusPill status={uiStatus(r.status)} />
    </div>
  );
}
