"use client";

/* Ride detail drawer for the driver: full trip + client + payment, with status
   actions (en route / complete / cancel / no-show) and Square capture. Plus a
   "Smart update" flow: drop screenshots of a client's change of plans → AI reads
   the change → conflict check → apply (re-quote + move calendar) → copy/send a
   change-confirmation message. */

import { useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  deleteRide,
  getRideDetail,
  previewRideUpdate,
  type PaymentMethod,
  type RideDetail as RD,
  type RideEdit,
  type RideUpdatePreview,
  updateRide,
} from "@/lib/booking";
import { extractReservation, hasAnyField, SmartError } from "@/lib/smart";
import { openMapsTo } from "@/lib/maps";
import { capturePayment, refundDecision } from "@/lib/payments";
import { StatusPill } from "./DashShell";
import { fmtWhen, uiStatus } from "./status";
import { RidePreferencesSummary } from "../web/RidePreferences";

const METHODS: PaymentMethod[] = ["cash", "square", "venmo", "zelle", "other"];
const SU_MAX_IMAGES = 5;

type Shot = { file: File; url: string };
type Mode = "view" | "capture" | "scanning" | "review" | "manual" | "confirm";

// A flat, editable snapshot of the ride fields the Smart update touches.
type Draft = {
  pickup: string;
  dropoff: string;
  when: string; // datetime-local string
  pax: string;
  flight: string;
  fare: string;
  notes: string;
};

const pad = (n: number) => String(n).padStart(2, "0");
function isoToLocal(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function localToIso(local: string): string | null {
  if (!local) return null;
  const d = new Date(local);
  return isNaN(d.getTime()) ? null : d.toISOString();
}

// Merge AI-extracted human date/time onto the ride's current schedule. Missing
// parts keep the current value; unparseable input leaves the schedule untouched.
function mergeSchedule(currentIso: string | null, aiDate?: unknown, aiTime?: unknown): string {
  const base = currentIso ? new Date(currentIso) : new Date();
  if (isNaN(base.getTime())) return isoToLocal(currentIso);
  const dt = new Date(base.getTime());
  const time = aiTime != null ? String(aiTime) : "";
  const tm = /(\d{1,2}):(\d{2})/.exec(time);
  if (tm) {
    dt.setHours(Number(tm[1]));
    dt.setMinutes(Number(tm[2]));
  }
  const date = aiDate != null ? String(aiDate) : "";
  if (date) {
    const parsed = new Date(/\d{4}/.test(date) ? date : `${date} ${base.getFullYear()}`);
    if (!isNaN(parsed.getTime())) {
      dt.setFullYear(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
  }
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function draftOf(ride: RD): Draft {
  return {
    pickup: ride.pickup || "",
    dropoff: ride.dropoff || "",
    when: isoToLocal(ride.scheduled_at),
    pax: ride.pax != null ? String(ride.pax) : "",
    flight: ride.flight_number || "",
    fare: ride.fare_total != null ? String(Math.round(ride.fare_total)) : "",
    notes: ride.notes || "",
  };
}

// The minimal change set (vs the original ride) to PATCH / preview.
function changesFrom(d: Draft, orig: Draft): RideEdit {
  const c: RideEdit = {};
  if (d.pickup.trim() && d.pickup !== orig.pickup) c.pickup = d.pickup.trim();
  if (d.dropoff.trim() && d.dropoff !== orig.dropoff) c.dropoff = d.dropoff.trim();
  if (d.when && d.when !== orig.when) c.scheduled_at = localToIso(d.when);
  if (d.pax !== orig.pax) c.pax = d.pax ? Number(d.pax) : null;
  if (d.flight !== orig.flight) c.flight_number = d.flight.trim() || null;
  if (d.notes !== orig.notes) c.notes = d.notes.trim() || null;
  if (d.fare !== orig.fare && d.fare) c.fare_override = Number(d.fare);
  return c;
}

// Bilingual change-confirmation message (mirrors AddRide's bvConfirmationMsg).
function changeMsg(ride: RD): string {
  const es = String(ride.lang || "EN").toUpperCase() === "ES";
  const name = ride.client?.name || ride.passenger_name || "";
  const first = name.trim().split(/\s+/)[0] || "";
  const when = fmtWhen(ride.scheduled_at);
  const route = `${ride.pickup || "—"} → ${ride.dropoff || "—"}`;
  const flight = ride.flight_number ? (es ? `Vuelo ${ride.flight_number}` : `Flight ${ride.flight_number}`) : "";
  const pax = ride.pax ? (es ? `${ride.pax} pasajero(s)` : `${ride.pax} passenger(s)`) : "";
  const extra = [flight, pax].filter(Boolean).join(" · ");
  const fare = ride.fare_total ? (es ? `Tarifa $${Math.round(ride.fare_total)}.` : `Fare $${Math.round(ride.fare_total)}.`) : "";
  if (es) {
    return `Hola${first ? " " + first : ""}, tu viaje con Black Volt Mobility fue ACTUALIZADO. Nuevos detalles:\n\n${when}\n${route}${extra ? "\n" + extra : ""}${fare ? "\n" + fare : ""}\n\nTu Kia EV9 negro llegará puntual. Responde si algo más cambia.\n— Black Volt Mobility · Poder silencioso, llegada premium.`;
  }
  return `Hi${first ? " " + first : ""}, your Black Volt Mobility ride has been UPDATED. New details:\n\n${when}\n${route}${extra ? "\n" + extra : ""}${fare ? "\n" + fare : ""}\n\nYour blacked-out Kia EV9 will arrive on time. Reply if anything else changes.\n— Black Volt Mobility · Silent power, premium arrival.`;
}

function Row({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5, color: "var(--silver)", minWidth: 0 }}>
      <Icon name={icon} size={15} color="var(--volt)" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{children}</span>
    </div>
  );
}

export function RideDetail({
  rideId,
  onClose,
  onChanged,
}: {
  rideId: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { t, lang } = useI18n();
  const [ride, setRide] = useState<RD | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Smart update state.
  const [mode, setMode] = useState<Mode>("view");
  const [shots, setShots] = useState<Shot[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [orig, setOrig] = useState<Draft | null>(null);
  const [preview, setPreview] = useState<RideUpdatePreview | null>(null);
  const [demo, setDemo] = useState(false);
  const [suErr, setSuErr] = useState<string | null>(null);
  const [suNoRead, setSuNoRead] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => getRideDetail(rideId).then(setRide).catch(() => setErr("load"));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rideId]);

  const patch = async (body: RideEdit) => {
    setBusy(true);
    setErr(null);
    try {
      await updateRide(rideId, body);
      await load();
      onChanged?.();
    } catch {
      setErr("action");
    } finally {
      setBusy(false);
    }
  };
  const changeStatus = (status: string) => patch({ status });

  const del = async () => {
    if (typeof window !== "undefined" && !window.confirm(t("dash.ride.deleteConfirm"))) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteRide(rideId);
      onChanged?.();
      onClose();
    } catch {
      setErr("delete");
    } finally {
      setBusy(false);
    }
  };

  const capture = async () => {
    if (!ride?.payment) return;
    setBusy(true);
    setErr(null);
    try {
      await capturePayment(ride.payment.id);
      await load();
      onChanged?.();
    } catch {
      setErr("capture");
    } finally {
      setBusy(false);
    }
  };

  const refund = async (feePct: number) => {
    if (!ride?.payment) return;
    setBusy(true);
    setErr(null);
    try {
      await refundDecision(ride.id, feePct);
      await load();
      onChanged?.();
    } catch {
      setErr("refund");
    } finally {
      setBusy(false);
    }
  };

  // ── Smart update helpers ──────────────────────────────────────────────────
  const addFiles = (files: FileList | File[]) => {
    setSuErr(null);
    setShots((prev) => {
      const room = SU_MAX_IMAGES - prev.length;
      if (room <= 0) return prev;
      const next = Array.from(files)
        .filter((f) => f.type.startsWith("image/"))
        .slice(0, room)
        .map((file) => ({ file, url: URL.createObjectURL(file) }));
      return [...prev, ...next];
    });
  };
  const clearShots = () =>
    setShots((prev) => {
      prev.forEach((s) => URL.revokeObjectURL(s.url));
      return [];
    });
  const closeSmart = () => {
    clearShots();
    setDraft(null);
    setOrig(null);
    setPreview(null);
    setDemo(false);
    setErr(null);
    setSuErr(null);
    setSuNoRead(false);
    setMode("view");
  };
  // Manual update: open the same editable form as the Smart review, pre-filled
  // with the ride's current values, skipping the screenshot/AI capture step.
  const startManual = () => {
    if (!ride) return;
    const d = draftOf(ride);
    setOrig(d);
    setDraft(d);
    setPreview(null);
    setDemo(false);
    setSuNoRead(false);
    setErr(null);
    setMode("manual");
  };
  useEffect(() => () => shots.forEach((s) => URL.revokeObjectURL(s.url)), []); // eslint-disable-line react-hooks/exhaustive-deps

  // Paste-to-add while capturing.
  useEffect(() => {
    if (mode !== "capture") return;
    const onPaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const pics = Array.from(items)
        .filter((it) => it.type?.startsWith("image"))
        .map((it) => it.getAsFile())
        .filter((f): f is File => !!f);
      if (pics.length) addFiles(pics);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [mode]);

  const SU_ERR_CODES = ["unsupported_image_type", "image_too_large", "decode_failed"];
  const runExtract = async () => {
    if (!ride || !shots.length) return;
    setMode("scanning");
    setErr(null);
    setSuErr(null);
    setSuNoRead(false);
    let fields: Record<string, unknown> = {};
    try {
      const res = await extractReservation(shots.map((s) => s.file));
      fields = res.fields || {};
      setDemo(res.simulated);
      if (!hasAnyField(fields)) setSuNoRead(true);
    } catch (e) {
      // Hard failure: stay on capture with a clear, actionable message.
      const code = e instanceof SmartError && SU_ERR_CODES.includes(e.code) ? e.code : "service";
      setSuErr(`dash.ride.su.err.${code}`);
      setMode("capture");
      return;
    }
    const base = draftOf(ride);
    const next: Draft = { ...base };
    const has = (v: unknown) => v != null && String(v).trim() !== "";
    if (has(fields.pickup)) next.pickup = String(fields.pickup);
    if (has(fields.dropoff)) next.dropoff = String(fields.dropoff);
    if (has(fields.date) || has(fields.time)) next.when = mergeSchedule(ride.scheduled_at, fields.date, fields.time);
    if (has(fields.passengers)) next.pax = String(fields.passengers);
    if (has(fields.flight)) next.flight = String(fields.flight);
    if (has(fields.fare)) next.fare = String(fields.fare);
    if (has(fields.notes)) next.notes = String(fields.notes);
    setOrig(base);
    setDraft(next);
    setMode("review");
  };

  // Re-quote + conflict check whenever the draft changes in review/manual edit.
  useEffect(() => {
    if ((mode !== "review" && mode !== "manual") || !draft || !orig) return;
    const changes = changesFrom(draft, orig);
    if (Object.keys(changes).length === 0) {
      setPreview(null);
      return;
    }
    let alive = true;
    const id = setTimeout(() => {
      previewRideUpdate(rideId, changes)
        .then((p) => alive && setPreview(p))
        .catch(() => alive && setPreview(null));
    }, 450);
    return () => {
      alive = false;
      clearTimeout(id);
    };
  }, [mode, draft, orig, rideId]);

  const applyUpdate = async () => {
    if (!draft || !orig) return;
    const changes = changesFrom(draft, orig);
    if (Object.keys(changes).length === 0) {
      setErr("unchanged");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await updateRide(rideId, changes);
      await load();
      onChanged?.();
      clearShots();
      setMode("confirm");
    } catch {
      setErr("action");
    } finally {
      setBusy(false);
    }
  };

  const bucket = ride ? uiStatus(ride.status) : "upcoming";
  const canEnRoute = ["requested", "quoted", "confirmed", "assigned"].includes(ride?.status || "");
  const canComplete = ride?.status === "en_route";
  const canCancel = bucket === "upcoming" || bucket === "active";
  const canDelete = bucket === "cancelled";
  const canSmartUpdate = bucket === "upcoming" || bucket === "active";
  const pay = ride?.payment;

  const shell = (children: React.ReactNode) => (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 70, background: "rgba(5,5,9,0.72)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 460, maxHeight: "88dvh", overflowY: "auto", background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-volt)", padding: 24, position: "relative" }}
      >
        <button onClick={onClose} aria-label="Close" style={{ position: "absolute", top: 16, right: 16, background: "none", border: "none", cursor: "pointer", padding: 4 }}>
          <Icon name="x" size={18} color="var(--silver)" />
        </button>
        {children}
      </div>
    </div>
  );

  if (!ride) {
    return shell(
      <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
        {err ? t("dash.ride.loadErr") : t("common.loading")}
      </div>,
    );
  }

  // ── Smart update: capture / scanning ──────────────────────────────────────
  if (mode === "capture" || mode === "scanning") {
    return shell(
      <>
        {suErr && mode === "capture" && (
          <div style={{ display: "flex", alignItems: "center", gap: 9, background: "rgba(255,99,99,0.08)", border: "1px solid rgba(255,99,99,0.4)", borderRadius: "var(--radius-md)", padding: "11px 13px", marginBottom: 12 }}>
            <Icon name="alert-circle" size={15} color="var(--danger)" />
            <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{t(suErr)}</span>
          </div>
        )}
        <SmartCapturePanel
          t={t}
          shots={shots}
          scanning={mode === "scanning"}
          fileRef={fileRef}
          onFiles={addFiles}
          onRemove={(i) => setShots((prev) => { const s = prev[i]; if (s) URL.revokeObjectURL(s.url); return prev.filter((_, j) => j !== i); })}
          onExtract={runExtract}
          onBack={closeSmart}
        />
      </>,
    );
  }

  // ── Smart update / Manual update: editable diff + conflicts ─────────────────
  if ((mode === "review" || mode === "manual") && draft && orig) {
    const manual = mode === "manual";
    const changes = changesFrom(draft, orig);
    const changedKeys = new Set(Object.keys(changes));
    const conflicts = preview?.conflicts || [];
    const newFare = preview?.proposed?.fare_total;
    const set = (k: keyof Draft, v: string) => setDraft((d) => (d ? { ...d, [k]: v } : d));
    return shell(
      <>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
          <Icon name={manual ? "pencil" : "sparkles"} size={18} color="var(--volt)" />
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 18, color: "var(--arctic)" }}>{manual ? t("dash.ride.manualUpdate") : t("dash.ride.su.review")}</span>
        </div>
        <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 16 }}>BV-{ride.id}</div>
        {demo && (
          <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="alert-circle" size={12} color="var(--fg3)" />
            {t("dash.ride.su.demo")}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
          <EditField label={t("dash.ride.su.f.pickup")} icon="circle-dot" changed={changedKeys.has("pickup")} t={t} value={draft.pickup} onChange={(v) => set("pickup", v)} />
          <EditField label={t("dash.ride.su.f.dropoff")} icon="map-pin" changed={changedKeys.has("dropoff")} t={t} value={draft.dropoff} onChange={(v) => set("dropoff", v)} />
          <EditField label={t("dash.ride.su.f.scheduled_at")} icon="calendar" type="datetime-local" changed={changedKeys.has("scheduled_at")} t={t} value={draft.when} onChange={(v) => set("when", v)} />
          <div style={{ display: "flex", gap: 10 }}>
            <EditField label={t("dash.ride.su.f.pax")} icon="users" type="number" changed={changedKeys.has("pax")} t={t} value={draft.pax} onChange={(v) => set("pax", v)} />
            <EditField label={t("dash.ride.su.f.flight_number")} icon="plane" changed={changedKeys.has("flight_number")} t={t} value={draft.flight} onChange={(v) => set("flight", v)} />
          </div>
          <EditField label={t("dash.ride.su.f.fare_total")} icon="dollar-sign" type="number" prefix="$" changed={changedKeys.has("fare_override")} t={t} value={draft.fare} onChange={(v) => set("fare", v.replace(/[^0-9.]/g, ""))} />
          <EditField label={t("dash.ride.su.f.notes")} icon="message-circle" changed={changedKeys.has("notes")} t={t} value={draft.notes} onChange={(v) => set("notes", v)} />
        </div>

        {newFare != null && changedKeys.size > 0 && (
          <div style={{ fontSize: 12.5, color: "var(--silver)", marginBottom: 12 }}>
            {t("dash.ride.su.f.fare_total")}: <strong style={{ color: "var(--volt)" }}>${Math.round(newFare)}</strong>
            {preview?.proposed?.distance_miles != null ? ` · ${preview.proposed.distance_miles} mi` : ""}
          </div>
        )}

        {conflicts.length > 0 && (
          <div style={{ background: "rgba(255,194,75,0.08)", border: "1px solid rgba(255,194,75,0.4)", borderRadius: "var(--radius-md)", padding: "12px 14px", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: 13, color: "var(--warning)", marginBottom: 6 }}>
              <Icon name="alert-circle" size={15} color="var(--warning)" />
              {t("dash.ride.su.conflict")}
            </div>
            <div style={{ fontSize: 12, color: "var(--silver)", marginBottom: 6 }}>{t("dash.ride.su.conflictSub")}</div>
            {conflicts.map((c) => (
              <div key={c.id} style={{ fontSize: 12.5, color: "var(--arctic)" }}>
                • {c.name} — {fmtWhen(c.scheduled_at)}
              </div>
            ))}
          </div>
        )}

        {err && (
          <div style={{ fontSize: 12.5, color: "var(--danger)", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="alert-circle" size={14} color="var(--danger)" />
            {t(`dash.ride.err.${err}`)}
          </div>
        )}

        <div style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
          <Button variant="ghost" icon="arrow-left" disabled={busy} onClick={manual ? closeSmart : () => { clearShots(); setMode("capture"); }}>
            {t("dash.ride.su.back")}
          </Button>
          {changedKeys.size === 0 ? (
            <span style={{ fontSize: 12.5, color: suNoRead ? "var(--warning)" : "var(--fg3)", alignSelf: "center" }}>
              {suNoRead ? t("dash.ride.su.noRead") : t("dash.ride.su.unchanged")}
            </span>
          ) : (
            <Button
              variant={conflicts.length ? "tint" : "solid"}
              icon={conflicts.length ? "alert-circle" : "check"}
              disabled={busy}
              onClick={applyUpdate}
            >
              {busy ? t("dash.ride.su.applying") : conflicts.length ? t("dash.ride.su.applyAnyway") : t("dash.ride.su.apply")}
            </Button>
          )}
        </div>
      </>,
    );
  }

  // ── Smart update: change confirmation ──────────────────────────────────────
  if (mode === "confirm") {
    return shell(<ChangeConfirm ride={ride} t={t} onDone={closeSmart} />);
  }

  // ── Default view ───────────────────────────────────────────────────────────
  return shell(
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--arctic)" }}>
          {ride.client?.name || ride.passenger_name || t("dash.ride.guest")}
        </span>
        <StatusPill status={ride.overdue ? "overdue" : bucket} />
      </div>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 16 }}>BV-{ride.id}</div>

      {ride.overdue && (
        <div style={{ display: "flex", alignItems: "center", gap: 9, background: "rgba(255,138,61,0.1)", border: "1px solid rgba(255,138,61,0.4)", borderRadius: "var(--radius-md)", padding: "11px 13px", marginBottom: 16 }}>
          <Icon name="alert-circle" size={15} color="#FF8A3D" />
          <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{t("dash.ride.overdueNotice")}</span>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 11, marginBottom: 18 }}>
        <Row icon="circle-dot">{ride.pickup}</Row>
        <Row icon="map-pin">{ride.dropoff}</Row>
        <Row icon="calendar">{fmtWhen(ride.scheduled_at)}</Row>
        {ride.google_event_id && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--success)" }}>
            <Icon name="circle-check" size={14} color="var(--success)" />
            {t("dash.ride.onCalendar")}
          </div>
        )}
        {ride.distance_miles != null && (
          <Row icon="navigation">
            {ride.distance_miles} mi · {ride.duration_minutes != null ? `${Math.round(ride.duration_minutes)} min` : "—"}
          </Row>
        )}
        {ride.pax != null && <Row icon="users">{ride.pax}</Row>}
        {ride.flight_number && <Row icon="plane">{ride.flight_number}</Row>}
        {(ride.client?.phone || ride.client_phone) && <Row icon="phone">{ride.client?.phone || ride.client_phone}</Row>}
        {ride.notes && <Row icon="message-circle">{ride.notes}</Row>}
      </div>

      {(() => {
        // Show the ride's per-ride preferences, falling back to the client's standing ones.
        const prefs = ride.ride_preferences ?? ride.client?.preferences;
        return prefs ? <RidePreferencesSummary value={prefs} /> : null;
      })()}

      {/* Fare + payment */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderRadius: "var(--radius-md)", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("book.fare")}</div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--volt)" }}>${Math.round(ride.fare_total || 0)}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.ride.payment")}</div>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: ride.paid ? "var(--success)" : "var(--fg3)" }}>
            {ride.paid ? t("dash.ride.paidYes") : t("dash.ride.paidNo")}
            {pay?.simulated ? " ·sim" : ""}
          </div>
        </div>
      </div>

      {/* Event deposit reservation: driver collects the remaining balance in person */}
      {ride.balance_due_cents != null ? (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: "var(--radius-md)",
            background: "var(--obsidian-3)",
            border: "1px solid var(--volt)",
            marginBottom: 16,
            fontSize: 13.5,
          }}
        >
          <div style={{ fontWeight: 700, color: "var(--volt)", marginBottom: 4 }}>
            {lang === "es" ? "Reserva de evento · depósito" : "Event reservation · deposit"}
          </div>
          <div style={{ color: "var(--fg2)" }}>
            {lang === "es"
              ? `Depósito pagado $${Math.round((ride.deposit_cents || 0) / 100)}. Cobra el saldo de $${Math.round(
                  ride.balance_due_cents / 100,
                )} el día del evento.`
              : `Deposit paid $${Math.round((ride.deposit_cents || 0) / 100)}. Collect the $${Math.round(
                  ride.balance_due_cents / 100,
                )} balance on the event day.`}
          </div>
        </div>
      ) : null}

      {/* Payment method + mark paid */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>{t("dash.ride.method")}</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {METHODS.map((m) => {
            const on = (ride.payment_method || "cash") === m;
            return (
              <button
                key={m}
                disabled={busy}
                onClick={() => patch({ payment_method: m })}
                style={{ padding: "7px 13px", borderRadius: "var(--radius-full)", cursor: "pointer", fontSize: 12.5, fontWeight: 600, fontFamily: "var(--font-sans)", background: on ? "var(--volt-bg-20)" : "var(--obsidian-3)", color: on ? "var(--volt)" : "var(--silver)", border: `1px solid ${on ? "var(--volt-border)" : "var(--line-strong)"}` }}
              >
                {t(`dash.method.${m}`)}
              </button>
            );
          })}
        </div>
        <button
          disabled={busy}
          onClick={() => patch({ paid: !ride.paid })}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", borderRadius: "var(--radius-md)", cursor: "pointer", fontSize: 13.5, fontWeight: 600, fontFamily: "var(--font-sans)", width: "100%", justifyContent: "center", background: ride.paid ? "rgba(43,212,160,0.12)" : "var(--obsidian-3)", color: ride.paid ? "var(--success)" : "var(--silver)", border: `1px solid ${ride.paid ? "rgba(43,212,160,0.4)" : "var(--line-strong)"}` }}
        >
          <Icon name={ride.paid ? "circle-check" : "circle-dot"} size={16} color="currentColor" />
          {ride.paid ? t("dash.ride.markUnpaid") : t("dash.ride.markPaid")}
        </button>
      </div>

      {err && (
        <div style={{ fontSize: 12.5, color: "var(--danger)", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="alert-circle" size={14} color="var(--danger)" />
          {t(`dash.ride.err.${err}`)}
        </div>
      )}

      {/* Refund decision (cancelled <24h, card still authorized/captured) */}
      {ride.status === "cancelled" &&
        ride.cancellation_fee_eligible &&
        pay &&
        (pay.status === "authorized" || pay.status === "captured") &&
        (() => {
          const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;
          const keep20 = pay.amount * 0.2;
          const keep30 = pay.amount * 0.3;
          return (
            <div style={{ background: "rgba(255,194,75,0.08)", border: "1px solid rgba(255,194,75,0.4)", borderRadius: "var(--radius-md)", padding: "12px 14px", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: 13, color: "var(--warning)", marginBottom: 6 }}>
                <Icon name="alert-circle" size={15} color="var(--warning)" />
                {t("dash.ride.refund.title")}
              </div>
              <div style={{ fontSize: 12, color: "var(--silver)", marginBottom: 10 }}>{t("dash.ride.refund.note")}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <Button variant="ghost" icon="rotate-ccw" disabled={busy} onClick={() => refund(0)}>
                  {t("dash.ride.refund.full")}
                </Button>
                <Button variant="solid" icon="dollar-sign" disabled={busy} onClick={() => refund(20)}>
                  {`${t("dash.ride.refund.fee20")} · ${money(keep20)}`}
                </Button>
                <Button variant="solid" icon="dollar-sign" disabled={busy} onClick={() => refund(30)}>
                  {`${t("dash.ride.refund.fee30")} · ${money(keep30)}`}
                </Button>
              </div>
            </div>
          );
        })()}

      {/* Actions */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {(bucket === "upcoming" || bucket === "active") && ride.pickup && (
          <Button variant="tint" icon="navigation" onClick={() => openMapsTo(ride.pickup)}>
            {t("dash.ride.navigate")}
          </Button>
        )}
        {ride.overdue && (
          <Button variant="solid" icon="circle-check" disabled={busy} onClick={() => changeStatus("completed")}>
            {t("dash.ride.confirmPickup")}
          </Button>
        )}
        {canSmartUpdate && (
          <Button variant="solid" icon="sparkles" disabled={busy} onClick={() => setMode("capture")}>
            {t("dash.ride.smartUpdate")}
          </Button>
        )}
        {canSmartUpdate && (
          <Button variant="tint" icon="pencil" disabled={busy} onClick={startManual}>
            {t("dash.ride.manualUpdate")}
          </Button>
        )}
        {pay?.status === "authorized" && (
          <Button variant="solid" icon="credit-card" disabled={busy} onClick={capture}>{t("dash.ride.capture")}</Button>
        )}
        {canEnRoute && (
          <Button variant="tint" icon="navigation" disabled={busy} onClick={() => changeStatus("en_route")}>{t("dash.ride.enroute")}</Button>
        )}
        {canComplete && (
          <Button variant="solid" icon="circle-check" disabled={busy} onClick={() => changeStatus("completed")}>{t("dash.ride.complete")}</Button>
        )}
        {canCancel && (
          <Button variant="ghost" icon="x" disabled={busy} onClick={() => changeStatus("cancelled")}>{t("dash.ride.cancel")}</Button>
        )}
        {canDelete && (
          <Button variant="ghost" icon="trash-2" disabled={busy} onClick={del}>
            {busy ? t("dash.ride.deleting") : t("dash.ride.delete")}
          </Button>
        )}
      </div>
    </>,
  );
}

function EditField({
  label, icon, value, onChange, changed, type, prefix, t,
}: {
  label: string; icon: string; value: string; onChange: (v: string) => void;
  changed?: boolean; type?: string; prefix?: string; t: (k: string) => string;
}) {
  return (
    <label style={{ display: "block", flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
        <span style={{ fontSize: 11.5, color: "var(--fg3)" }}>{label}</span>
        {changed && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9.5, fontWeight: 700, letterSpacing: "0.06em", color: "var(--volt)", background: "var(--volt-bg)", border: "1px solid var(--volt-border)", borderRadius: 4, padding: "0 5px" }}>
            <Icon name="sparkles" size={9} color="var(--volt)" />AI
          </span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--obsidian-3)", borderRadius: "var(--radius-md)", padding: "9px 11px", border: `1px solid ${changed ? "var(--volt-border)" : "var(--line-strong)"}` }}>
        <Icon name={icon} size={15} color={changed ? "var(--volt)" : "var(--silver)"} />
        {prefix && <span style={{ color: "var(--silver)", fontSize: 13.5 }}>{prefix}</span>}
        <input
          type={type || "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", color: "var(--arctic)", fontSize: 13.5, fontFamily: "var(--font-sans)" }}
        />
      </div>
    </label>
  );
}

function SmartCapturePanel({
  t, shots, scanning, fileRef, onFiles, onRemove, onExtract, onBack,
}: {
  t: (k: string) => string; shots: Shot[]; scanning: boolean;
  fileRef: React.RefObject<HTMLInputElement>;
  onFiles: (f: FileList | File[]) => void; onRemove: (i: number) => void;
  onExtract: () => void; onBack: () => void;
}) {
  const pick = () => fileRef.current?.click();
  const input = (
    <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: "none" }}
      onChange={(e) => { if (e.target.files?.length) onFiles(e.target.files); e.target.value = ""; }} />
  );
  if (scanning) {
    return (
      <div style={{ padding: "26px 0", textAlign: "center" }}>
        <div style={{ width: 46, height: 46, margin: "0 auto 14px", borderRadius: "50%", border: "2px solid var(--volt-border)", borderTopColor: "var(--volt)", animation: "bv-spin 0.9s linear infinite" }} />
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--arctic)" }}>{t("dash.ride.su.reading")}</div>
      </div>
    );
  }
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
        <Icon name="sparkles" size={18} color="var(--volt)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 18, color: "var(--arctic)" }}>{t("dash.ride.su.title")}</span>
      </div>
      <p style={{ fontSize: 13, color: "var(--silver)", margin: "0 0 16px", lineHeight: 1.5 }}>{t("dash.ride.su.sub")}</p>

      {shots.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(90px, 1fr))", gap: 8, marginBottom: 14 }}>
          {shots.map((s, i) => (
            <div key={s.url} style={{ position: "relative", borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--line)", background: "var(--void)", aspectRatio: "3 / 4" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={s.url} alt={`shot ${i + 1}`} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
              <button onClick={() => onRemove(i)} style={{ position: "absolute", top: 4, right: 4, width: 22, height: 22, borderRadius: "50%", border: "none", cursor: "pointer", background: "rgba(10,10,15,0.78)", color: "var(--arctic)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon name="x" size={12} color="currentColor" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files?.length) onFiles(e.dataTransfer.files); }}
        onClick={pick}
        style={{ border: "2px dashed var(--line-strong)", borderRadius: "var(--radius-md)", background: "var(--obsidian-3)", padding: "22px 16px", textAlign: "center", cursor: "pointer", marginBottom: 16 }}
      >
        <Icon name="image" size={24} color="var(--volt)" />
        <div style={{ fontSize: 13, color: "var(--silver)", marginTop: 8 }}>
          {shots.length ? t("dash.ride.su.add") : t("dash.ride.su.choose")}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
        <Button variant="ghost" icon="arrow-left" onClick={onBack}>{t("dash.ride.su.back")}</Button>
        <Button variant="solid" icon="sparkles" disabled={!shots.length} onClick={onExtract}>{t("dash.ride.su.extract")}</Button>
      </div>
      {input}
    </>
  );
}

function ChangeConfirm({ ride, t, onDone }: { ride: RD; t: (k: string) => string; onDone: () => void }) {
  const msg = changeMsg(ride);
  const [copied, setCopied] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const phone = ride.client?.phone || ride.client_phone || null;
  const email = ride.client?.email || null;
  const copy = () => {
    const done = () => { setCopied(true); setTimeout(() => setCopied(false), 1800); };
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(msg).then(done, done);
    else done();
  };
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
        <Icon name="circle-check" size={18} color="var(--success)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 18, color: "var(--arctic)" }}>{t("dash.ride.su.applied")}</span>
      </div>
      <div style={{ fontSize: 13, color: "var(--fg3)", marginBottom: 14 }}>{t("dash.ride.cm.sub")}</div>

      <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>
        <Icon name="message-circle" size={14} color="var(--volt)" />
        {t("dash.ride.cm.title")}
      </div>
      <div style={{ background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", borderTopLeftRadius: 4, padding: "13px 15px", whiteSpace: "pre-line", fontSize: 13, lineHeight: 1.55, color: "var(--silver)", marginBottom: 14 }}>
        {msg}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <Button variant={copied ? "ghost" : "solid"} icon={copied ? "check" : "clipboard"} onClick={copy}>
          {copied ? t("dash.ride.cm.copied") : t("dash.ride.cm.copy")}
        </Button>
        {phone && <Button variant="tint" icon="message-circle" onClick={() => setSent("sms")}>{t("dash.ride.cm.sms")}</Button>}
        {email && <Button variant="tint" icon="message-circle" onClick={() => setSent("email")}>{t("dash.ride.cm.email")}</Button>}
        {phone && <Button variant="tint" icon="phone" onClick={() => setSent("call")}>{t("dash.ride.cm.call")}</Button>}
      </div>

      {sent && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(43,212,160,0.08)", border: "1px solid rgba(43,212,160,0.4)", borderRadius: "var(--radius-md)", padding: "10px 13px", marginBottom: 10 }}>
          <Icon name="circle-check" size={15} color="var(--success)" />
          <div style={{ fontSize: 12.5, color: "var(--silver)" }}>
            <strong style={{ color: "var(--arctic)" }}>{t("dash.ride.cm.sent")}</strong> · {t("dash.ride.cm.staged")}
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Button variant="ghost" icon="check" onClick={onDone}>{t("dash.ride.cm.done")}</Button>
      </div>
    </>
  );
}
