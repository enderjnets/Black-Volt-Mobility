"use client";

import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import {
  AdminEvent,
  patchEvent,
  pricingPreview,
  runResearch,
  RoundTripPreview,
  ResearchResult,
} from "@/lib/events";

import { Button, Field, Pill } from "../ui";

const money = (n: number) => `$${Math.round(n)}`;

/** Per-event pricing controls: fees, round-trip suggestion, and Uber research. */
export function EventPricingPanel({ e }: { e: AdminEvent }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const [eventFee, setEventFee] = useState(String(e.event_fee ?? 0));
  const [nightFee, setNightFee] = useState(String(e.night_fee ?? 25));
  const [nightCutoff, setNightCutoff] = useState(e.night_cutoff ?? "21:00");
  const [waitPerHour, setWaitPerHour] = useState(String(e.wait_fee_per_hour ?? 30));
  const [estHours, setEstHours] = useState(String(e.est_duration_hours ?? 3));
  const [rtPrice, setRtPrice] = useState(
    e.round_trip_price != null ? String(e.round_trip_price) : "",
  );

  const [preview, setPreview] = useState<RoundTripPreview | null>(null);
  const [research, setResearch] = useState<ResearchResult | null>(e.pricing_research);
  const [error, setError] = useState<string | null>(null);

  async function savePricing() {
    setBusy(true);
    setError(null);
    try {
      const patch: Partial<AdminEvent> = {
        event_fee: Number(eventFee) || 0,
        night_fee: Number(nightFee) || 0,
        night_cutoff: nightCutoff,
        wait_fee_per_hour: Number(waitPerHour) || 0,
        est_duration_hours: Number(estHours) || 0,
      };
      if (rtPrice.trim() !== "") patch.round_trip_price = Number(rtPrice) || 0;
      await patchEvent(e.id, patch);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch {
      setError(t("dash.events.pricing.err"));
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await pricingPreview(e.id));
    } catch {
      setError(t("dash.events.pricing.err"));
    } finally {
      setBusy(false);
    }
  }

  async function doResearch() {
    setBusy(true);
    setError(null);
    try {
      setResearch(await runResearch(e.id));
    } catch {
      setError(t("dash.events.pricing.err"));
    } finally {
      setBusy(false);
    }
  }

  const box = {
    marginTop: 14,
    paddingTop: 14,
    borderTop: "1px solid var(--line-strong)",
  } as const;
  const grid = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
    gap: 8,
    marginTop: 10,
  } as const;

  return (
    <div style={box}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: "none", border: "none", color: "var(--volt)", fontSize: 13,
          cursor: "pointer", padding: 0, fontWeight: 600,
        }}
      >
        {open ? "▾ " : "▸ "}
        {t("dash.events.pricing.title")}
      </button>

      {open && (
        <>
          <div style={grid}>
            <Field label={t("dash.events.pricing.eventFee")} value={eventFee}
              onChange={setEventFee} type="number" />
            <Field label={t("dash.events.pricing.nightFee")} value={nightFee}
              onChange={setNightFee} type="number" />
            <Field label={t("dash.events.pricing.nightCutoff")} value={nightCutoff}
              onChange={setNightCutoff} placeholder="21:00" />
            <Field label={t("dash.events.pricing.waitPerHour")} value={waitPerHour}
              onChange={setWaitPerHour} type="number" />
            <Field label={t("dash.events.pricing.estHours")} value={estHours}
              onChange={setEstHours} type="number" />
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <Button onClick={savePricing} disabled={busy}>
              {saved ? t("dash.events.saved") : t("dash.events.pricing.save")}
            </Button>
            <Button variant="ghost" onClick={loadPreview} disabled={busy}>
              {t("dash.events.pricing.preview")}
            </Button>
            <Button variant="ghost" onClick={doResearch} disabled={busy}>
              {t("dash.events.pricing.research")}
            </Button>
          </div>

          {error && (
            <div style={{ color: "var(--danger, #ff6b6b)", fontSize: 12, marginTop: 8 }}>{error}</div>
          )}

          {preview && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 6 }}>
                {t("dash.events.pricing.suggested")}
              </div>
              {preview.lines.map((l, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "var(--fg3)" }}>
                    {l.label}
                    {l.qty ? ` ×${l.qty}` : ""}
                  </span>
                  <span style={{ color: "var(--silver)" }}>{money(l.amount)}</span>
                </div>
              ))}
              <div
                style={{
                  display: "flex", justifyContent: "space-between", marginTop: 6,
                  paddingTop: 6, borderTop: "1px solid var(--line-strong)", fontWeight: 700,
                }}
              >
                <span>{t("dash.events.pricing.total")}</span>
                <span style={{ color: "var(--volt)" }}>{money(preview.total)}</span>
              </div>
              {preview.capped && (
                <div style={{ marginTop: 6 }}>
                  <Pill tone="warning">
                    {t("dash.events.pricing.capped")}
                    {preview.uber_black ? ` (Uber ${money(preview.uber_black)})` : ""}
                  </Pill>
                </div>
              )}
              <div style={{ marginTop: 10 }}>
                <Field label={t("dash.events.pricing.rtPrice")} value={rtPrice}
                  onChange={setRtPrice} type="number"
                  hint={t("dash.events.pricing.rtHint")} />
              </div>
            </div>
          )}

          {research && research.zones.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 6 }}>
                {t("dash.events.pricing.research.title")}
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ color: "var(--fg3)", textAlign: "left" }}>
                      <th style={{ padding: "4px 6px" }}>{t("dash.events.pricing.col.zone")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.events.pricing.col.ours")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.events.pricing.col.uber")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.events.pricing.col.margin")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.events.pricing.col.score")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {research.zones.map((z) => (
                      <tr key={z.key} style={{ borderTop: "1px solid var(--line-strong)" }}>
                        <td style={{ padding: "4px 6px", color: "var(--silver)" }}>
                          {z.name}{" "}
                          <span style={{ color: "var(--fg3)" }}>({z.distance_from_base_mi} mi)</span>
                        </td>
                        <td style={{ padding: "4px 6px" }}>{money(z.our_round_trip)}</td>
                        <td style={{ padding: "4px 6px" }}>
                          {money(z.uber_round_trip)}
                          <span style={{ color: "var(--fg3)", marginLeft: 4 }}>
                            {z.method === "live" ? "●" : "○"}
                          </span>
                        </td>
                        <td style={{ padding: "4px 6px", color: z.margin_pct >= 0 ? "var(--volt)" : "#ff6b6b" }}>
                          {z.margin_pct}%
                        </td>
                        <td style={{ padding: "4px 6px" }}>{z.score.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {research.recommendation && (
                <p style={{ marginTop: 10, fontSize: 13, color: "var(--silver)", lineHeight: 1.5 }}>
                  {research.recommendation}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
