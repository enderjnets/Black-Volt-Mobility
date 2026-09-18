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

export function LogTab() {
  const { t } = useI18n();
  const [today, setToday] = useState<TodayLog | null>(null);
  const [busy, setBusy] = useState<LogKind | null>(null);
  const [product, setProduct] = useState<Product>("black");
  const [accepted, setAccepted] = useState(false);
  const [fare, setFare] = useState("");
  const [flash, setFlash] = useState<"saved" | "failed" | null>(null);
  const wakeLock = useRef<{ release: () => Promise<void> } | null>(null);

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

  const send = useCallback(
    async (kind: LogKind, extra: Partial<Parameters<typeof logEvent>[0]> = {}) => {
      setBusy(kind);
      const pos = await getPosition();
      try {
        await logEvent({
          client_event_id: newEventId(),
          kind,
          lat: pos?.lat ?? null,
          lng: pos?.lng ?? null,
          ...extra,
        });
        setFlash("saved");
      } catch {
        setFlash("failed");
      } finally {
        setBusy(null);
        setTimeout(() => setFlash(null), 1800);
        refresh();
      }
    },
    [refresh],
  );

  // Auto-ping while waiting and this screen is visible; a wake lock keeps the
  // screen on so the ping loop survives (best effort — iOS ignores it when hidden).
  const waiting = today?.state === "open";
  useEffect(() => {
    if (!waiting) return;
    let alive = true;
    const tick = () => {
      if (!alive || document.visibilityState !== "visible") return;
      send("ping");
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
  }, [waiting, send]);

  const sendOffer = async () => {
    const f = fare.trim() ? Number(fare) : null;
    await send("offer", { product, accepted, fare: Number.isFinite(f as number) ? f : null });
    setAccepted(false);
    setFare("");
  };

  const disabled = busy !== null;

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
    opacity: disabled ? 0.55 : 1,
  };

  const secondaryBtn = (active: boolean, tone: "volt" | "warn"): React.CSSProperties => ({
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
    opacity: disabled ? 0.55 : 1,
  });

  const chip = (on: boolean): React.CSSProperties => ({
    padding: "10px 14px",
    borderRadius: 999,
    border: `1px solid ${on ? "var(--volt)" : "var(--line-strong)"}`,
    background: on ? "rgba(0,229,255,0.12)" : "transparent",
    color: on ? "var(--volt)" : "var(--silver)",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    opacity: disabled ? 0.55 : 1,
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
        <button style={offerBtn} disabled={disabled} onClick={sendOffer}>
          <Icon name="bell" size={24} color="currentColor" />
          {t("dash.demand.log.offer")}
        </button>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {PRODUCTS.map((p) => (
            <button key={p} style={chip(product === p)} disabled={disabled} onClick={() => setProduct(p)}>
              {t(`dash.demand.product.${p}`)}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button style={chip(accepted)} disabled={disabled} onClick={() => setAccepted((a) => !a)}>
            <Icon name="check" size={14} color="currentColor" /> {t("dash.demand.log.accepted")}
          </button>
          <input
            inputMode="decimal"
            placeholder={t("dash.demand.log.fare")}
            value={fare}
            onChange={(e) => setFare(e.target.value)}
            style={{ flex: 1, minWidth: 0, padding: "10px 12px", borderRadius: 10, border: "1px solid var(--line-strong)", background: "transparent", color: "var(--arctic)" }}
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <button style={secondaryBtn(today?.state === "open", "volt")} disabled={disabled} onClick={() => send("online")}>
          <Icon name="zap" size={18} color="currentColor" />
          {t("dash.demand.log.online")}
        </button>
        <button style={secondaryBtn(false, "volt")} disabled={disabled} onClick={() => send("here")}>
          <Icon name="map-pin" size={18} color="currentColor" />
          {t("dash.demand.log.here")}
        </button>
        <button style={secondaryBtn(false, "warn")} disabled={disabled} onClick={() => send("offline")}>
          <Icon name="x" size={18} color="currentColor" />
          {t("dash.demand.log.offline")}
        </button>
      </div>

      <div style={{ fontSize: 12, color: "var(--silver)" }}>{t("dash.demand.log.hint")}</div>

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
                <button onClick={() => send("here")} style={{ marginLeft: "auto", ...chip(false), padding: "4px 10px", fontSize: 12 }}>
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
