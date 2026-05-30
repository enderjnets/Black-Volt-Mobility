"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { Button, Card, Field } from "../ui";
import { useI18n } from "@/lib/i18n";

export function MapPlaceholder({ height = 200 }: { height?: number }) {
  return (
    <div
      style={{
        position: "relative",
        height,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: "1px solid var(--line-strong)",
        background:
          "repeating-linear-gradient(0deg, rgba(199,203,212,0.04) 0 1px, transparent 1px 28px), repeating-linear-gradient(90deg, rgba(199,203,212,0.04) 0 1px, transparent 1px 28px), var(--obsidian)",
      }}
    >
      <svg
        viewBox="0 0 320 200"
        preserveAspectRatio="none"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      >
        <path
          d="M40 160 C 110 150, 120 70, 200 60 S 280 40, 286 36"
          fill="none"
          stroke="#00E5FF"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeOpacity="0.9"
        />
      </svg>
      <div style={{ position: "absolute", left: 30, bottom: 48 }}>
        <Icon name="circle-dot" size={18} color="var(--volt)" />
      </div>
      <div style={{ position: "absolute", right: 26, top: 22 }}>
        <Icon name="map-pin" size={20} color="var(--volt)" fill="rgba(0,229,255,0.15)" />
      </div>
    </div>
  );
}

function StepDots({ step }: { step: number }) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: i === step ? 22 : 7,
            height: 7,
            borderRadius: 99,
            background: i <= step ? "var(--volt)" : "var(--obsidian-3)",
            transition: "all .2s ease-out",
          }}
        />
      ))}
    </div>
  );
}

function Stat({ icon, label, value, accent }: { icon: string; label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ flex: 1 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          color: "var(--fg3)",
          fontSize: 12,
          marginBottom: 6,
          fontFamily: "var(--font-sans)",
        }}
      >
        <Icon name={icon} size={14} color="var(--silver)" /> {label}
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 26,
          color: accent ? "var(--volt)" : "var(--arctic)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
    </div>
  );
}

export function Booking() {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("Denver Intl (DEN)");
  const [when, setWhen] = useState("now");
  const [pax, setPax] = useState(2);

  return (
    <div style={{ maxWidth: 480, margin: "0 auto", padding: "32px 0" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 28, color: "var(--arctic)", margin: 0 }}>
          {step === 3 ? t("book.confirmed") : t("book.title")}
        </h2>
        {step < 3 && <StepDots step={step} />}
      </div>

      <Card glow pad={22}>
        {step === 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Field icon="circle-dot" label={t("book.from")} value={from} placeholder={t("book.from.ph")} onChange={setFrom} />
            <Field icon="plane" label={t("book.to")} value={to} placeholder={t("book.to.ph")} onChange={setTo} />
            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{t("book.when")}</div>
                <div style={{ display: "flex", gap: 8 }}>
                  {[
                    ["now", t("book.now")],
                    ["schedule", t("book.schedule")],
                  ].map(([v, l]) => (
                    <button
                      key={v}
                      onClick={() => setWhen(v)}
                      style={{
                        flex: 1,
                        padding: "11px 0",
                        borderRadius: "var(--radius-md)",
                        cursor: "pointer",
                        fontFamily: "var(--font-sans)",
                        fontSize: 13,
                        fontWeight: 600,
                        background: when === v ? "var(--volt-bg-20)" : "var(--obsidian-3)",
                        color: when === v ? "var(--volt)" : "var(--silver)",
                        border: `1px solid ${when === v ? "var(--volt-border)" : "var(--line-strong)"}`,
                      }}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ width: 120 }}>
                <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{t("book.pax")}</div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "var(--obsidian-3)",
                    border: "1px solid var(--line-strong)",
                    borderRadius: "var(--radius-md)",
                    padding: "6px 10px",
                  }}
                >
                  <button
                    onClick={() => setPax(Math.max(1, pax - 1))}
                    style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
                  >
                    –
                  </button>
                  <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--arctic)", fontSize: 16 }}>
                    {pax}
                  </span>
                  <button
                    onClick={() => setPax(Math.min(6, pax + 1))}
                    style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
            <Button variant="solid" full size="lg" iconRight="arrow-right" onClick={() => setStep(1)}>
              {t("book.review")}
            </Button>
          </div>
        )}

        {step === 1 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <MapPlaceholder height={190} />
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--silver)" }}>
                <Icon name="circle-dot" size={16} color="var(--volt)" /> {from || "Downtown Denver"}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--silver)" }}>
                <Icon name="plane" size={16} color="var(--volt)" /> {to}
              </div>
            </div>
            <div style={{ display: "flex", gap: 16, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
              <Stat icon="navigation" label={t("book.distance")} value="18.4 mi" />
              <Stat icon="clock" label={t("book.eta")} value="6 min" />
              <Stat icon="dollar-sign" label={t("book.fare")} value="$74" accent />
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <Button variant="plain" icon="arrow-left" onClick={() => setStep(0)}>
                {t("common.back")}
              </Button>
              <Button variant="solid" full iconRight="arrow-right" onClick={() => setStep(2)}>
                {t("book.pay")}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ color: "var(--silver)", fontSize: 14 }}>{t("book.fare")}</span>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 32, color: "var(--arctic)" }}>
                $74<span style={{ fontSize: 14, color: "var(--fg3)", fontWeight: 400 }}> .00</span>
              </span>
            </div>
            <Field icon="user" label="Cardholder" value="Alex Rivera" readOnly />
            <Field icon="credit-card" label="Card" value="4242  4242  4242  4242" readOnly />
            <Button variant="solid" full size="lg" icon="zap" onClick={() => setStep(3)}>
              {t("book.paybtn")}
            </Button>
            <div
              style={{
                textAlign: "center",
                fontSize: 11,
                color: "var(--fg3)",
                textTransform: "uppercase",
                letterSpacing: "0.18em",
                fontFamily: "var(--font-display)",
                fontWeight: 600,
              }}
            >
              {t("book.silent")}
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ textAlign: "center", padding: "10px 0 6px" }}>
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                margin: "0 auto 18px",
                background: "var(--volt-bg)",
                border: "1px solid var(--volt-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "var(--shadow-volt)",
              }}
            >
              <Icon name="check" size={32} color="var(--volt)" />
            </div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: 22,
                color: "var(--arctic)",
                marginBottom: 8,
              }}
            >
              {t("book.confirmed")}
            </div>
            <p style={{ color: "var(--silver)", fontSize: 14, maxWidth: 300, margin: "0 auto 18px", lineHeight: 1.5 }}>
              {t("book.confirmed.sub")}
            </p>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 16,
                padding: "14px 0",
                borderTop: "1px solid var(--line)",
                borderBottom: "1px solid var(--line)",
              }}
            >
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--volt)" }}>6 min</div>
                <div style={{ fontSize: 11, color: "var(--fg3)" }}>ETA</div>
              </div>
              <div style={{ width: 1, height: 30, background: "var(--line-strong)" }} />
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--arctic)" }}>
                  Kia EV9
                </div>
                <div style={{ fontSize: 11, color: "var(--fg3)" }}>Black · ENV-4827</div>
              </div>
            </div>
            <div style={{ marginTop: 18 }}>
              <Button variant="ghost" full onClick={() => setStep(0)}>
                {t("book.another")}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
