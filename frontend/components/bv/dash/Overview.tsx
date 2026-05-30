"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { useI18n } from "@/lib/i18n";
import { useViewport } from "@/lib/useViewport";
import { StatusPill } from "./DashShell";
import { BV_RIDES, type Ride } from "./data";

function KpiCard({ icon, label, value, sub, accent }: { icon: string; label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 180,
        background: "var(--obsidian)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-lg)",
        padding: 18,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ fontSize: 12, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "var(--font-sans)" }}>
          {label}
        </span>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "var(--volt-bg)",
            border: "1px solid var(--volt-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon name={icon} size={16} color="var(--volt)" />
        </div>
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 32,
          color: accent ? "var(--volt)" : "var(--arctic)",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 12, color: "var(--silver)", marginTop: 8, display: "flex", alignItems: "center", gap: 5 }}>
          <Icon name="trending-up" size={13} color="var(--success)" /> {sub}
        </div>
      )}
    </div>
  );
}

export function RideRow({ r }: { r: Ride }) {
  const [h, setH] = useState(false);
  const { compact } = useViewport();

  if (compact) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "13px 14px",
          margin: "0 6px 8px",
          background: "var(--obsidian-2)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
        }}
      >
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: "50%",
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon name="user" size={17} color="var(--silver)" />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", whiteSpace: "nowrap" }}>
              {r.client}
            </span>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)" }}>${r.fare}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--silver)", minWidth: 0, margin: "2px 0 6px" }}>
            <Icon name="circle-dot" size={12} color="var(--volt)" />
            <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {r.from} → {r.to}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "var(--fg3)" }}>{r.time}</span>
            <StatusPill status={r.status} />
            {r.flight && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--silver)" }}>
                <Icon name="plane" size={11} color="var(--volt)" />
                {r.flight}
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "130px 1fr 100px 60px 104px",
        alignItems: "center",
        gap: 12,
        padding: "13px 16px",
        borderRadius: "var(--radius-md)",
        background: h ? "var(--obsidian-2)" : "transparent",
        transition: "background .12s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: "50%",
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon name="user" size={16} color="var(--silver)" />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", whiteSpace: "nowrap" }}>
            {r.client}
          </div>
          <div style={{ fontSize: 11, color: "var(--fg3)" }}>{r.time}</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--silver)", minWidth: 0, overflow: "hidden" }}>
        <Icon name="circle-dot" size={14} color="var(--volt)" />
        <span style={{ whiteSpace: "nowrap", flexShrink: 0 }}>{r.from}</span>
        <Icon name="arrow-right" size={13} color="var(--fg3)" />
        <span style={{ whiteSpace: "nowrap", flexShrink: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{r.to}</span>
      </div>
      <div style={{ fontSize: 12, color: r.flight ? "var(--silver)" : "var(--fg3)", display: "flex", alignItems: "center", gap: 6 }}>
        {r.flight ? (
          <>
            <Icon name="plane" size={13} color="var(--volt)" />
            {r.flight}
          </>
        ) : (
          "—"
        )}
      </div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--arctic)" }}>${r.fare}</div>
      <StatusPill status={r.status} />
    </div>
  );
}

function MiniBars() {
  const data = [40, 62, 48, 80, 95, 70, 55];
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  const max = Math.max(...data);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 90 }}>
      {data.map((v, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: "100%",
              height: `${(v / max) * 70}px`,
              borderRadius: 4,
              background: i === 4 ? "var(--volt)" : "var(--obsidian-3)",
              boxShadow: i === 4 ? "var(--shadow-volt-sm)" : "none",
            }}
          />
          <span style={{ fontSize: 11, color: "var(--fg3)" }}>{days[i]}</span>
        </div>
      ))}
    </div>
  );
}

export function Overview() {
  const { t } = useI18n();
  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="bv-kpi-row" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <KpiCard icon="navigation" label={t("dash.kpi.rides")} value="6" sub={t("dash.kpi.ridesSub")} />
        <KpiCard icon="dollar-sign" label={t("dash.kpi.revenue")} value="$434" sub={t("dash.kpi.revenueSub")} accent />
        <KpiCard icon="star" label={t("dash.kpi.rating")} value="4.98" />
        <KpiCard icon="clock" label={t("dash.kpi.next")} value="14:20" sub={t("dash.kpi.nextSub")} />
      </div>

      <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1.7fr 1fr", gap: 20, alignItems: "start" }}>
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: "6px 6px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px 8px" }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--arctic)" }}>{t("dash.today")}</span>
            <span style={{ fontSize: 12, color: "var(--volt)", cursor: "pointer" }}>{t("dash.viewAll")}</span>
          </div>
          {BV_RIDES.slice(0, 5).map((r) => (
            <RideRow key={r.id} r={r} />
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 18, boxShadow: "var(--shadow-volt)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <Icon name="sparkles" size={16} color="var(--volt)" />
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{t("dash.ai")}</span>
            </div>
            <p style={{ fontSize: 13, color: "var(--silver)", lineHeight: 1.55, margin: "0 0 14px" }}>{t("dash.ai.suggest")}</p>
            <div style={{ display: "flex", gap: 8 }}>
              <Button variant="solid" size="sm">
                {t("dash.ai.reschedule")}
              </Button>
              <Button variant="plain" size="sm">
                {t("dash.ai.dismiss")}
              </Button>
            </div>
          </div>
          <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)", marginBottom: 14 }}>{t("dash.week")}</div>
            <MiniBars />
          </div>
        </div>
      </div>
    </div>
  );
}
