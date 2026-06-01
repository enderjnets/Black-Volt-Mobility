"use client";

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Pill, Toggle } from "../ui";
import { useI18n } from "@/lib/i18n";
import { getRateConfig, updateRateConfig } from "@/lib/booking";

function RateInput({
  icon,
  label,
  hint,
  value,
  setValue,
  step = 1,
  prefix,
  min = 0,
}: {
  icon: string;
  label: string;
  hint?: string;
  value: number;
  setValue: (v: number) => void;
  step?: number;
  prefix?: string;
  min?: number;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 0", borderBottom: "1px solid var(--line)" }}>
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 9,
          background: "var(--volt-bg)",
          border: "1px solid var(--volt-border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon name={icon} size={17} color="var(--volt)" />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>{label}</div>
        {hint && <div style={{ fontSize: 12, color: "var(--fg3)" }}>{hint}</div>}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: "5px 8px",
        }}
      >
        <button
          onClick={() => setValue(Math.max(min, +(value - step).toFixed(2)))}
          style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, lineHeight: 1, width: 20 }}
        >
          –
        </button>
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 16,
            color: "var(--arctic)",
            minWidth: 58,
            textAlign: "center",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {prefix}
          {value}
        </span>
        <button
          onClick={() => setValue(+(value + step).toFixed(2))}
          style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, lineHeight: 1, width: 20 }}
        >
          +
        </button>
      </div>
    </div>
  );
}

export function Rates() {
  const { t } = useI18n();
  const [base, setBase] = useState(12);
  const [perMile, setPerMile] = useState(2.4);
  const [perMin, setPerMin] = useState(0.55);
  const [airport, setAirport] = useState(74);
  const [minimum, setMinimum] = useState(28);
  const [surge, setSurge] = useState(true);
  const [surgeX, setSurgeX] = useState(1.4);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load the tenant's live rate config; falls back to the defaults above.
  useEffect(() => {
    getRateConfig()
      .then((rc) => {
        setBase(rc.base);
        setPerMile(rc.per_mile);
        setPerMin(rc.per_minute);
        setAirport(rc.airport_flat);
        setMinimum(rc.minimum);
        setSurge(rc.peak_enabled);
        setSurgeX(rc.peak_multiplier);
      })
      .catch(() => {});
  }, []);

  const SAMPLE_MI = 18.4;
  const SAMPLE_MIN = 28;
  const fare = Math.max(minimum, airport);

  const save = async () => {
    setSaving(true);
    try {
      await updateRateConfig({
        base,
        per_mile: perMile,
        per_minute: perMin,
        airport_flat: airport,
        minimum,
        peak_enabled: surge,
        peak_multiplier: surgeX,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch {
      /* keep the form values; a transient save error shouldn't wipe them */
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bv-dash-grid" style={{ padding: 28, display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 22, alignItems: "start" }}>
      <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: "18px 22px 22px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--arctic)" }}>{t("dash.rates.engine")}</span>
          <Pill tone="muted" icon="dollar-sign">
            USD
          </Pill>
        </div>
        <RateInput icon="dollar-sign" label={t("dash.rates.base")} hint={t("dash.rates.baseHint")} value={base} setValue={setBase} step={1} prefix="$" />
        <RateInput icon="navigation" label={t("dash.rates.perMile")} hint={t("dash.rates.perMileHint")} value={perMile} setValue={setPerMile} step={0.1} prefix="$" />
        <RateInput icon="clock" label={t("dash.rates.perMin")} hint={t("dash.rates.perMinHint")} value={perMin} setValue={setPerMin} step={0.05} prefix="$" />
        <RateInput icon="plane" label={t("dash.rates.airport")} hint={t("dash.rates.airportHint")} value={airport} setValue={setAirport} step={1} prefix="$" />
        <RateInput icon="shield-check" label={t("dash.rates.min")} hint={t("dash.rates.minHint")} value={minimum} setValue={setMinimum} step={1} prefix="$" />

        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 0 4px" }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 9,
              background: surge ? "rgba(255,194,75,0.12)" : "var(--obsidian-3)",
              border: `1px solid ${surge ? "rgba(255,194,75,0.4)" : "var(--line-strong)"}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Icon name="trending-up" size={17} color={surge ? "var(--warning)" : "var(--silver)"} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)" }}>{t("dash.rates.surge")}</div>
            <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.rates.surgeHint", { x: surgeX })}</div>
          </div>
          {surge && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "var(--obsidian-3)",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--radius-md)",
                padding: "5px 8px",
                marginRight: 4,
              }}
            >
              <button
                onClick={() => setSurgeX(Math.max(1, +(surgeX - 0.1).toFixed(1)))}
                style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, width: 20 }}
              >
                –
              </button>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)", minWidth: 34, textAlign: "center" }}>
                ×{surgeX}
              </span>
              <button
                onClick={() => setSurgeX(+(surgeX + 0.1).toFixed(1))}
                style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, width: 20 }}
              >
                +
              </button>
            </div>
          )}
          <Toggle on={surge} setOn={setSurge} />
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 20, boxShadow: "var(--shadow-volt)" }}>
          <div style={{ fontSize: 12, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 6 }}>{t("dash.rates.preview")}</div>
          <div style={{ fontSize: 13, color: "var(--silver)", marginBottom: 14 }}>{t("dash.rates.sample", { mi: SAMPLE_MI, min: SAMPLE_MIN })}</div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 46, color: "var(--volt)", lineHeight: 1 }}>${fare}</div>
          <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 7 }}>
            {(
              [
                [t("dash.rates.base2"), base],
                [t("dash.rates.distance"), +(perMile * SAMPLE_MI).toFixed(2)],
                [t("dash.rates.time"), +(perMin * SAMPLE_MIN).toFixed(2)],
              ] as const
            ).map(([l, v]) => (
              <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span style={{ color: "var(--silver)" }}>{l}</span>
                <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--arctic)" }}>${v}</span>
              </div>
            ))}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--fg3)" }}>
              <span>{t("dash.rates.denFlat")}</span>
              <span>${airport}</span>
            </div>
          </div>
        </div>

        <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)", marginBottom: 12 }}>{t("dash.rates.accent")}</div>
          <div style={{ display: "flex", gap: 10 }}>
            {["#00E5FF", "#2BD4A0", "#FFC24B", "#FF5C6E"].map((c, i) => (
              <div
                key={c}
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 8,
                  background: c,
                  cursor: "pointer",
                  boxShadow: i === 0 ? "0 0 0 2px var(--void), 0 0 0 4px var(--volt)" : "none",
                }}
              />
            ))}
          </div>
          <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 12 }}>{t("dash.rates.accentHint")}</div>
        </div>

        <Button variant="solid" full size="lg" icon={saved ? "check" : "zap"} disabled={saving} onClick={save}>
          {saved ? t("dash.rates.saved") : t("dash.rates.save")}
        </Button>
      </div>
    </div>
  );
}
