"use client";

/* One-tap shift log. This is the screen that sits next to Uber Driver in Android
   split-screen, so: no header, Offer is the primary control (first, largest, its
   chips + Accepted toggle always visible), Online/Here/Offline are a secondary
   row. Every tap gets a client id so a retried POST is a no-op. */

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import {
  type LogEvent,
  type LogKind,
  type Product,
  PRODUCTS,
  type TodayLog,
  getToday,
  logEvent,
  newEventId,
} from "@/lib/demand";

const GPS_TIMEOUT_MS = 8000;
const PING_MS = 60_000;

type Pos = { lat: number; lng: number } | null;

function getPosition(): Promise<Pos> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: GPS_TIMEOUT_MS, maximumAge: 15_000 },
    );
  });
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

async function postLog(kind: LogKind, extra: Partial<Parameters<typeof logEvent>[0]> = {}): Promise<void> {
  const pos = await getPosition();
  await logEvent({
    client_event_id: newEventId(),
    kind,
    lat: pos?.lat ?? null,
    lng: pos?.lng ?? null,
    ...extra,
  });
}

export function LogTab() {
  const { t } = useI18n();
  const [today, setToday] = useState<TodayLog | null>(null);
  const [busy, setBusy] = useState<LogKind | null>(null);
  const [product, setProduct] = useState<Product>("black");
  const [accepted, setAccepted] = useState(false);
  const [fare, setFare] = useState("");
  const [flash, setFlash] = useState<"saved" | "failed" | null>(null);
  const wakeLock = useRef<{ release: () => Promise<void> } | null>(null);
  const pingInFlight = useRef(false);

  const refresh = useCallback(async () => {
    try {
      setToday(await getToday());
    } catch {
      /* keep the last known state; the next tap refreshes */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Next to Uber Driver in split-screen, the shell's own sticky header and fixed
  // tab bar cost too much of a ~390×400 viewport; drop them for this tab only.
  useEffect(() => {
    document.documentElement.dataset.bvCompact = "log";
    return () => {
      delete document.documentElement.dataset.bvCompact;
    };
  }, []);

  const send = useCallback(
    async (kind: LogKind, extra: Partial<Parameters<typeof logEvent>[0]> = {}): Promise<boolean> => {
      setBusy(kind);
      let ok = false;
      try {
        await postLog(kind, extra);
        setFlash("saved");
        ok = true;
      } catch {
        setFlash("failed");
      } finally {
        setBusy(null);
        setTimeout(() => setFlash(null), 1800);
        refresh();
      }
      return ok;
    },
    [refresh],
  );

  // Auto-ping has its own in-flight guard, never the tap `busy` state — an offer
  // arriving mid-ping must find every button live. A still-running ping just
  // skips the next tick instead of piling up requests.
  const sendPing = useCallback(async () => {
    if (pingInFlight.current) return;
    pingInFlight.current = true;
    try {
      await postLog("ping");
      setFlash("saved");
    } catch {
      setFlash("failed"); // the owner must know when his waits stop being counted
    } finally {
      pingInFlight.current = false;
      setTimeout(() => setFlash(null), 1800);
      refresh();
    }
  }, [refresh]);

  // Auto-ping while waiting and this screen is visible; a wake lock keeps the
  // screen on so the ping loop survives (best effort — iOS ignores it when hidden).
  const waiting = today?.state === "open";
  useEffect(() => {
    if (!waiting) return;
    let alive = true;
    const tick = () => {
      if (!alive || document.visibilityState !== "visible") return;
      sendPing();
    };
    const id = setInterval(tick, PING_MS);
    (async () => {
      try {
        const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } };
        if (nav.wakeLock) wakeLock.current = await nav.wakeLock.request("screen");
      } catch {
        /* unsupported or denied: pings still run while visible */
      }
    })();
    return () => {
      alive = false;
      clearInterval(id);
      wakeLock.current?.release().catch(() => {});
      wakeLock.current = null;
    };
  }, [waiting, sendPing]);

  const sendOffer = async () => {
    const raw = fare.trim().replace(",", ".");
    const f = raw ? Number(raw) : null;
    const ok = await send("offer", { product, accepted, fare: Number.isFinite(f as number) ? f : null });
    if (ok) {
      setAccepted(false);
      setFare("");
    }
  };

  // Per-kind, not global: a slow GPS fix on one button must not freeze the
  // others — see the auto-ping comment above for why. The product chips and
  // Accepted toggle are local state that only offer's request cares about.
  const offerDisabled = busy === "offer";
  const onlineDisabled = busy === "online";
  const hereDisabled = busy === "here";
  const offlineDisabled = busy === "offline";

  const offerBtn: React.CSSProperties = {
    minHeight: 76,
    width: "100%",
    borderRadius: 14,
    border: "1px solid var(--volt)",
    background: "rgba(0,229,255,0.14)",
    color: "var(--volt)",
    fontFamily: "var(--font-display)",
    fontSize: 22,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    cursor: "pointer",
    WebkitTapHighlightColor: "transparent",
    opacity: offerDisabled ? 0.55 : 1,
  };

  const secondaryBtn = (active: boolean, tone: "volt" | "warn", dim: boolean): React.CSSProperties => ({
    minHeight: 56,
    borderRadius: 12,
    border: `1px solid ${active ? "var(--volt)" : "var(--line-strong)"}`,
    background: tone === "warn" ? "rgba(255,90,90,0.08)" : active ? "rgba(0,229,255,0.10)" : "var(--obsidian)",
    color: tone === "warn" ? "#ff7a7a" : active ? "var(--volt)" : "var(--arctic)",
    fontFamily: "var(--font-display)",
    fontSize: 13,
    fontWeight: 700,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    cursor: "pointer",
    WebkitTapHighlightColor: "transparent",
    opacity: dim ? 0.55 : 1,
  });

  const chip = (on: boolean, dim: boolean): React.CSSProperties => ({
    minHeight: 36,
    padding: "10px 12px",
    borderRadius: 999,
    border: `1px solid ${on ? "var(--volt)" : "var(--line-strong)"}`,
    background: on ? "rgba(0,229,255,0.12)" : "transparent",
    color: on ? "var(--volt)" : "var(--silver)",
    fontWeight: 600,
    fontSize: 13,
    whiteSpace: "nowrap",
    cursor: "pointer",
    opacity: dim ? 0.55 : 1,
  });

  const stateKey =
    today?.state === "open" ? "dash.demand.log.state.open"
    : today?.state === "enroute" ? "dash.demand.log.state.enroute"
    : "dash.demand.log.state.offline";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13, color: "var(--silver)" }}>
        <span>
          {t(stateKey)}
          {today?.open_since ? ` ${fmtTime(today.open_since)}` : ""}
        </span>
        <span style={{ color: flash === "failed" ? "#ff7a7a" : "var(--volt)", minHeight: 16 }}>
          {flash === "saved" ? t("dash.demand.log.saved") : flash === "failed" ? t("dash.demand.log.failed") : ""}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 12, borderRadius: 14, border: "1px solid var(--volt-border)", background: "rgba(0,229,255,0.05)" }}>
        <button style={offerBtn} disabled={offerDisabled} onClick={sendOffer}>
          <Icon name="bell" size={24} color="currentColor" />
          {t("dash.demand.log.offer")}
        </button>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {PRODUCTS.map((p) => (
            <button
              key={p}
              style={chip(product === p, offerDisabled)}
              disabled={offerDisabled}
              aria-pressed={product === p}
              onClick={() => setProduct(p)}
            >
              {t(`dash.demand.product.${p}`)}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            style={chip(accepted, offerDisabled)}
            disabled={offerDisabled}
            aria-pressed={accepted}
            onClick={() => setAccepted((a) => !a)}
          >
            <Icon name="check" size={14} color="currentColor" /> {t("dash.demand.log.accepted")}
          </button>
          <input
            inputMode="decimal"
            placeholder={t("dash.demand.log.fare")}
            aria-label={t("dash.demand.log.fare")}
            value={fare}
            onChange={(e) => setFare(e.target.value)}
            style={{ flex: 1, minWidth: 0, padding: "10px 12px", borderRadius: 10, border: "1px solid var(--line-strong)", background: "transparent", color: "var(--arctic)" }}
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <button style={secondaryBtn(today?.state === "open", "volt", onlineDisabled)} disabled={onlineDisabled} onClick={() => send("online")}>
          <Icon name="zap" size={18} color="currentColor" />
          {t("dash.demand.log.online")}
        </button>
        <button style={secondaryBtn(false, "volt", hereDisabled)} disabled={hereDisabled} onClick={() => send("here")}>
          <Icon name="map-pin" size={18} color="currentColor" />
          {t("dash.demand.log.here")}
        </button>
        <button style={secondaryBtn(false, "warn", offlineDisabled)} disabled={offlineDisabled} onClick={() => send("offline")}>
          <Icon name="x" size={18} color="currentColor" />
          {t("dash.demand.log.offline")}
        </button>
      </div>

      <div className="bv-log-hint" style={{ fontSize: 12, color: "var(--silver)" }}>{t("dash.demand.log.hint")}</div>

      {waiting && (
        <div style={{ fontSize: 12, color: "var(--silver)" }}>{t("dash.demand.log.autoPing")}</div>
      )}

      <div style={{ fontFamily: "var(--font-display)", fontSize: 14, fontWeight: 700, marginTop: 4 }}>
        {t("dash.demand.log.today")}
      </div>
      {!today || today.events.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.log.empty")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {today.events.map((e: LogEvent) => (
            <div key={`${e.kind}-${e.id}`} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, padding: "8px 10px", borderRadius: 10, background: "var(--obsidian)" }}>
              <span style={{ color: "var(--silver)", width: 48 }}>{fmtTime(e.at)}</span>
              <span style={{ fontWeight: 600 }}>{t(`dash.demand.log.${e.kind === "offer" ? "offer" : e.kind}`)}</span>
              {e.product && <span style={{ color: "var(--volt)" }}>{t(`dash.demand.product.${e.product}`)}</span>}
              {e.accepted && <Icon name="circle-check" size={14} color="var(--volt)" />}
              {e.fare != null && <span>${e.fare}</span>}
              {e.zone_key === "den_lot" && <span style={{ color: "var(--silver)" }}>{t("dash.demand.log.denLot")}</span>}
              {e.no_position && (
                <button onClick={() => send("here")} style={{ marginLeft: "auto", ...chip(false, hereDisabled), flexShrink: 0, padding: "4px 10px", fontSize: 12 }}>
                  {t("dash.demand.log.noPosition")} · {t("dash.demand.log.retry")}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
