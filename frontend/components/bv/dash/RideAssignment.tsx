"use client";

/* Hand a ride to another driver on the team, agree what they keep, and talk to them
   about it — all inside the ride drawer.

   The ride never changes owner: the customer, the money and control stay with whoever
   booked it. The owner sees the full split and can settle it; the assigned driver sees
   only their own cut. Both sides share an internal thread the passenger never sees. */
import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import {
  type AssignableDriver,
  type EarningsSplit,
  assignRide,
  listAssignableDrivers,
  previewEarnings,
  unassignRide,
  updatePayout,
} from "@/lib/assignment";
import {
  type InternalMessage,
  listInternalMessages,
  sendInternalMessage,
} from "@/lib/rideMessages";
import { Icon } from "../Icon";
import { Button } from "../ui";

// The four the owner asked for. Anything else goes in the free field next to them.
const SHARE_PRESETS = [100, 80, 70, 50] as const;

// The handful of things that always need saying on a ride. One tap = sent.
const QUICK_KEYS = [
  "onMyWay",
  "arrived",
  "pickedUp",
  "enRoute",
  "droppedOff",
  "runningLate",
  "noShow",
  "allGood",
] as const;

const label: CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: 0.4,
  textTransform: "uppercase",
  color: "var(--fg3)",
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginBottom: 10,
};

const card: CSSProperties = {
  padding: "14px 16px",
  borderRadius: "var(--radius-md)",
  background: "var(--obsidian-3)",
  border: "1px solid var(--line-strong)",
  marginBottom: 16,
};

function money(n: number | undefined): string {
  return n === undefined ? "—" : `$${n.toFixed(2)}`;
}

/* ── internal thread ─────────────────────────────────────────────────────── */
function InternalThread({
  rideId,
  onActivity,
}: {
  rideId: number;
  onActivity?: () => void;
}) {
  const { t } = useI18n();
  const [msgs, setMsgs] = useState<InternalMessage[]>([]);
  const [text, setText] = useState("");
  const [canWrite, setCanWrite] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const r = await listInternalMessages(rideId);
      setMsgs(r.messages);
      setCanWrite(r.can_write);
    } catch {
      /* a transient failure just leaves the thread as-is */
    }
  }, [rideId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs.length]);

  async function send(body: string) {
    const b = body.trim();
    if (!b || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const m = await sendInternalMessage(rideId, b);
      setMsgs((s) => [...s, m]);
      setText("");
      onActivity?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {/* Fixed height, not flex:1 — a scroll child inside a max-height flex column
          collapses to 0 (the bug that hid the notifications list). */}
      <div
        ref={scroller}
        style={{
          height: 200,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: "10px 2px",
        }}
      >
        {msgs.length === 0 && (
          <div style={{ margin: "auto", fontSize: 13, color: "var(--fg3)" }}>
            {t("ride.internal.empty")}
          </div>
        )}
        {msgs.map((m) => (
          <div
            key={m.id}
            style={{
              alignSelf: m.mine ? "flex-end" : "flex-start",
              maxWidth: "82%",
              padding: "8px 11px",
              borderRadius: 12,
              fontSize: 14,
              lineHeight: 1.35,
              background: m.mine ? "var(--volt-bg)" : "var(--obsidian)",
              border: `1px solid ${m.mine ? "var(--volt)" : "var(--line-strong)"}`,
              color: "var(--arctic)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {m.body}
          </div>
        ))}
      </div>

      {canWrite && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0" }}>
            {QUICK_KEYS.map((k) => (
              <button
                key={k}
                type="button"
                disabled={busy}
                onClick={() => send(t(`ride.internal.quick.${k}`))}
                style={{
                  padding: "7px 11px",
                  minHeight: 34,
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: busy ? "wait" : "pointer",
                  background: "var(--obsidian)",
                  border: "1px solid var(--line-strong)",
                  color: "var(--silver)",
                }}
              >
                {t(`ride.internal.quick.${k}`)}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(text);
                }
              }}
              placeholder={t("ride.chat.placeholder")}
              style={{
                flex: 1,
                minWidth: 0,
                padding: "10px 12px",
                borderRadius: "var(--radius-md)",
                background: "var(--void)",
                border: "1px solid var(--line-strong)",
                color: "var(--arctic)",
                fontSize: 14,
              }}
            />
            <button
              type="button"
              onClick={() => send(text)}
              disabled={busy || !text.trim()}
              aria-label={t("ride.chat.send")}
              style={{
                width: 44,
                height: 44,
                flexShrink: 0,
                display: "grid",
                placeItems: "center",
                borderRadius: "var(--radius-md)",
                background: "var(--volt-bg)",
                border: "1px solid var(--volt)",
                color: "var(--volt)",
                cursor: busy || !text.trim() ? "default" : "pointer",
              }}
            >
              <Icon name="send" size={17} />
            </button>
          </div>
        </>
      )}
      {err && (
        <div style={{ marginTop: 8, fontSize: 12, color: "var(--danger)" }}>{err}</div>
      )}
    </div>
  );
}

/* ── assign + split ──────────────────────────────────────────────────────── */
export function RideAssignment({
  rideId,
  fare,
  assigned,
  assignedDriverName,
  driverSharePct,
  payoutStatus,
  earnings,
  isOwner,
  onChanged,
}: {
  rideId: number;
  fare: number | null | undefined;
  assigned: boolean;
  assignedDriverName?: string | null;
  driverSharePct?: number | null;
  payoutStatus?: string | null;
  earnings?: EarningsSplit | null;
  isOwner: boolean;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const [drivers, setDrivers] = useState<AssignableDriver[]>([]);
  const [email, setEmail] = useState("");
  const [pct, setPct] = useState<number>(driverSharePct ?? 80);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<EarningsSplit | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  // Only the owner can assign, so only they need the driver list.
  useEffect(() => {
    if (!isOwner || !open || drivers.length) return;
    listAssignableDrivers()
      .then((d) => {
        setDrivers(d);
        setEmail((e) => e || d[0]?.email || "");
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [isOwner, open, drivers.length]);

  // Live preview of what each side keeps, before anything is saved.
  useEffect(() => {
    if (!isOwner || (!open && !assigned)) return;
    let alive = true;
    previewEarnings(rideId, pct)
      .then((p) => alive && setPreview(p))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [isOwner, open, assigned, rideId, pct]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onChanged?.();
      setOpen(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const shown = assigned ? earnings : preview;

  return (
    <div style={card}>
      <div style={label}>
        <Icon name="users" size={15} color="var(--volt)" />
        {t("ride.assign.title")}
      </div>

      {assigned ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 14, color: "var(--arctic)" }}>
            {t("ride.assign.assignedTo")}{" "}
            <strong>{assignedDriverName || t("ride.assign.aDriver")}</strong>
            {payoutStatus === "paid" && (
              <span style={{ marginLeft: 8, fontSize: 12, color: "var(--success)" }}>
                ✓ {t("ride.assign.paid")}
              </span>
            )}
          </div>

          {shown && (
            <div style={{ display: "grid", gap: 4, fontSize: 13 }}>
              {isOwner && (
                <>
                  <Row k={t("ride.assign.gross")} v={money(shown.gross)} />
                  <Row k={t("ride.assign.squareFee")} v={`− ${money(shown.square_fee)}`} />
                  {!!shown.tax_reserve && (
                    <Row k={t("ride.assign.taxReserve")} v={`− ${money(shown.tax_reserve)}`} />
                  )}
                  <Row k={t("ride.assign.net")} v={money(shown.net)} strong />
                </>
              )}
              <Row
                k={`${t("ride.assign.driverGets")} (${shown.driver_share_pct}%)`}
                v={money(shown.driver_amount)}
                accent
              />
              {isOwner && <Row k={t("ride.assign.youKeep")} v={money(shown.owner_amount)} />}
            </div>
          )}

          {isOwner && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <Button
                variant="ghost"
                onClick={() =>
                  run(() => updatePayout(rideId, { paid: payoutStatus !== "paid" }))
                }
                disabled={busy}
              >
                {payoutStatus === "paid"
                  ? t("ride.assign.markUnpaid")
                  : t("ride.assign.markPaid")}
              </Button>
              <Button variant="ghost" onClick={() => setOpen((v) => !v)} disabled={busy}>
                {t("ride.assign.changeShare")}
              </Button>
              <Button variant="ghost" onClick={() => run(() => unassignRide(rideId))} disabled={busy}>
                {t("ride.assign.takeBack")}
              </Button>
            </div>
          )}

          {isOwner && open && (
            <div>
              <SharePicker pct={pct} setPct={setPct} t={t} />
              <Button
                onClick={() => run(() => updatePayout(rideId, { driver_share_pct: pct }))}
                disabled={busy}
              >
                {t("ride.assign.saveShare")}
              </Button>
            </div>
          )}

          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <div style={{ ...label, marginBottom: 6 }}>
              <Icon name="message-circle" size={15} color="var(--volt)" />
              {t("ride.internal.title")}
            </div>
            <InternalThread rideId={rideId} onActivity={onChanged} />
          </div>
        </div>
      ) : isOwner ? (
        <div>
          {!open ? (
            <Button variant="ghost" onClick={() => setOpen(true)}>
              {t("ride.assign.cta")}
            </Button>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <select
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{
                  padding: "10px 12px",
                  borderRadius: "var(--radius-md)",
                  background: "var(--void)",
                  border: "1px solid var(--line-strong)",
                  color: "var(--arctic)",
                  fontSize: 14,
                }}
              >
                {drivers.length === 0 && <option value="">{t("ride.assign.noDrivers")}</option>}
                {drivers.map((d) => (
                  <option key={d.email} value={d.email}>
                    {d.name} — {d.email}
                  </option>
                ))}
              </select>

              <SharePicker pct={pct} setPct={setPct} t={t} />

              {preview && (
                <div style={{ display: "grid", gap: 4, fontSize: 13 }}>
                  <Row k={t("ride.assign.gross")} v={money(preview.gross)} />
                  <Row k={t("ride.assign.squareFee")} v={`− ${money(preview.square_fee)}`} />
                  {!!preview.tax_reserve && (
                    <Row k={t("ride.assign.taxReserve")} v={`− ${money(preview.tax_reserve)}`} />
                  )}
                  <Row k={t("ride.assign.net")} v={money(preview.net)} strong />
                  <Row
                    k={`${t("ride.assign.driverGets")} (${pct}%)`}
                    v={money(preview.driver_amount)}
                    accent
                  />
                  <Row k={t("ride.assign.youKeep")} v={money(preview.owner_amount)} />
                </div>
              )}

              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("ride.assign.notePlaceholder")}
                maxLength={400}
                style={{
                  padding: "10px 12px",
                  borderRadius: "var(--radius-md)",
                  background: "var(--void)",
                  border: "1px solid var(--line-strong)",
                  color: "var(--arctic)",
                  fontSize: 14,
                }}
              />

              <div style={{ display: "flex", gap: 8 }}>
                <Button
                  onClick={() => run(() => assignRide(rideId, email, pct, note))}
                  disabled={busy || !email}
                >
                  {t("ride.assign.confirm")}
                </Button>
                <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          )}
          {fare == null && (
            <div style={{ marginTop: 8, fontSize: 12, color: "var(--fg3)" }}>
              {t("ride.assign.noFare")}
            </div>
          )}
        </div>
      ) : null}

      {err && <div style={{ marginTop: 8, fontSize: 12, color: "var(--danger)" }}>{err}</div>}
    </div>
  );
}

function Row({
  k,
  v,
  strong,
  accent,
}: {
  k: string;
  v: string;
  strong?: boolean;
  accent?: boolean;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span style={{ color: "var(--fg3)" }}>{k}</span>
      <span
        style={{
          fontWeight: strong || accent ? 700 : 500,
          color: accent ? "var(--volt)" : "var(--arctic)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {v}
      </span>
    </div>
  );
}

function SharePicker({
  pct,
  setPct,
  t,
}: {
  pct: number;
  setPct: (n: number) => void;
  t: (k: string) => string;
}) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 6 }}>
        {t("ride.assign.sharePrompt")}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {SHARE_PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPct(p)}
            style={{
              padding: "8px 14px",
              minHeight: 38,
              borderRadius: 999,
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
              background: pct === p ? "var(--volt-bg)" : "var(--obsidian)",
              border: `1px solid ${pct === p ? "var(--volt)" : "var(--line-strong)"}`,
              color: pct === p ? "var(--volt)" : "var(--silver)",
            }}
          >
            {p}%
          </button>
        ))}
        <input
          type="number"
          min={0}
          max={100}
          value={pct}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (!Number.isNaN(n)) setPct(Math.max(0, Math.min(100, Math.round(n))));
          }}
          aria-label={t("ride.assign.sharePrompt")}
          style={{
            width: 74,
            minHeight: 38,
            padding: "8px 10px",
            borderRadius: "var(--radius-md)",
            background: "var(--void)",
            border: "1px solid var(--line-strong)",
            color: "var(--arctic)",
            fontSize: 13,
            textAlign: "center",
          }}
        />
      </div>
    </div>
  );
}
