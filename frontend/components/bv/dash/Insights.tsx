"use client";

/* Driver Insights — first-party usage analytics. Reads /api/v1/analytics/summary
   and renders KPIs, a pageviews timeseries, the booking funnel, top pages, and
   source/device/country breakdowns. Styled to match Overview. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Donut, FunnelChart, TrendChart } from "./charts";
import { useI18n } from "@/lib/i18n";
import { type AnalyticsSummary, type CountRow, getAnalyticsSummary } from "@/lib/analytics";

function msText(ms: number): string {
  if (!ms) return "0s";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

function Kpi({ icon, label, value, accent }: { icon: string; label: string; value: string; accent?: boolean }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 150,
        background: "var(--obsidian)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-lg)",
        padding: 18,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ fontSize: 12, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</span>
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
          fontSize: 30,
          color: accent ? "var(--volt)" : "var(--arctic)",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)", marginBottom: 14 }}>{title}</div>
      {children}
    </div>
  );
}

function BarList({ rows, empty }: { rows: { label: string; count: number }[]; empty: string }) {
  if (!rows.length) return <Empty text={empty} />;
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      {rows.map((r) => (
        <div key={r.label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 13, color: "var(--silver)", width: 120, flexShrink: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={r.label}>
            {r.label}
          </span>
          <div style={{ flex: 1, height: 8, borderRadius: 99, background: "var(--obsidian-3)", overflow: "hidden" }}>
            <div style={{ width: `${(r.count / max) * 100}%`, height: "100%", background: "var(--volt)", borderRadius: 99 }} />
          </div>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 13, color: "var(--arctic)", width: 34, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
            {r.count}
          </span>
        </div>
      ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div style={{ fontSize: 13, color: "var(--fg3)", padding: "8px 0" }}>{text}</div>;
}

function rowsOf(data: CountRow[], fallback: string): { label: string; count: number }[] {
  return data.map((d) => ({ label: d.value || fallback, count: d.count }));
}

const RANGES = [7, 30, 90];

export function Insights() {
  const { t } = useI18n();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);
  const [campaign, setCampaign] = useState("__all__");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(false);
    getAnalyticsSummary(days)
      .then((d) => alive && setData(d))
      .catch(() => alive && setErr(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [days]);

  const tt = data?.totals;
  const f = data?.funnel || {};
  const funnelSteps = [
    { key: "book_start", camp: "starts", label: t("dash.insights.f.start") },
    { key: "book_review", camp: "reviewed", label: t("dash.insights.f.review") },
    { key: "book_pay", camp: "paid", label: t("dash.insights.f.pay") },
    { key: "book_confirmed", camp: "confirmed", label: t("dash.insights.f.confirmed") },
  ] as const;
  const campaigns = data?.campaigns || [];
  const selCamp = campaigns.find((c) => c.campaign === campaign);
  // Funnel steps for the selected scope (all = global funnel; else the campaign row).
  const chartSteps = funnelSteps.map((s) => ({
    key: s.key,
    label: s.label,
    count: selCamp ? (selCamp[s.camp] as number) : f[s.key] || 0,
  }));

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 22 }}>
      {/* range selector */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.insights.subtitle")}</span>
        <div style={{ display: "flex", gap: 4, background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 4 }}>
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDays(r)}
              style={{
                padding: "7px 16px",
                borderRadius: "var(--radius-full)",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                border: "none",
                fontFamily: "var(--font-sans)",
                background: days === r ? "var(--volt-bg-20)" : "transparent",
                color: days === r ? "var(--volt)" : "var(--silver)",
                boxShadow: days === r ? "inset 0 0 0 1px var(--volt-border)" : "none",
              }}
            >
              {t("dash.insights.days", { n: r })}
            </button>
          ))}
        </div>
      </div>

      {err && <Empty text={t("dash.insights.error")} />}
      {loading && !data && <Empty text={t("common.loading")} />}

      {data && (
        <>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Kpi icon="users" label={t("dash.insights.visitors")} value={String(tt?.visitors ?? 0)} accent />
            <Kpi icon="layout-dashboard" label={t("dash.insights.sessions")} value={String(tt?.sessions ?? 0)} />
            <Kpi icon="trending-up" label={t("dash.insights.pageviews")} value={String(tt?.pageviews ?? 0)} />
            <Kpi icon="clock" label={t("dash.insights.avgtime")} value={msText(tt?.avg_session_ms ?? 0)} />
          </div>

          <Panel title={t("dash.insights.trafficOverTime")}>
            <TrendChart
              data={data.timeseries}
              labels={{ visitors: t("dash.insights.visitors"), pageviews: t("dash.insights.pageviews") }}
            />
          </Panel>

          <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "start" }}>
            <Panel title={t("dash.insights.funnel")}>
              {campaigns.length > 0 && (
                <select
                  value={campaign}
                  onChange={(e) => setCampaign(e.target.value)}
                  style={{
                    width: "100%",
                    marginBottom: 14,
                    padding: "8px 10px",
                    fontSize: 13,
                    color: "var(--arctic)",
                    background: "var(--obsidian-3)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-md)",
                  }}
                >
                  <option value="__all__">{t("dash.insights.campaign.all")}</option>
                  {campaigns.map((c) => (
                    <option key={c.campaign} value={c.campaign}>
                      {c.campaign === "(none)" ? t("dash.insights.campaign.none") : c.campaign} · {c.starts}
                    </option>
                  ))}
                </select>
              )}

              <FunnelChart
                steps={chartSteps}
                ofLabel={t("dash.insights.funnel.ofPrev")}
                dropLabel={t("dash.insights.funnel.dropoff")}
              />

              <div style={{ borderTop: "1px solid var(--line)", marginTop: 12, paddingTop: 10, fontSize: 12.5, color: "var(--fg3)", display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="message-circle" size={13} color="var(--success)" />
                {t("dash.insights.signins", { n: f["sign_in"] || 0 })}
              </div>
              {(f["book_pay_failed"] || 0) > 0 && (
                <div style={{ fontSize: 12.5, color: "var(--danger)", display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
                  <Icon name="alert-circle" size={13} color="var(--danger)" />
                  {t("dash.insights.payfailed", { n: f["book_pay_failed"] || 0 })}
                </div>
              )}

              {campaigns.length > 0 && (
                <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                  <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>
                    {t("dash.insights.campaign.title")}
                  </div>
                  <div style={{ display: "grid", gap: 4 }}>
                    {campaigns.map((c) => {
                      const conv = c.starts > 0 ? Math.round((c.confirmed / c.starts) * 100) : 0;
                      const on = campaign === c.campaign;
                      return (
                        <button
                          key={c.campaign}
                          onClick={() => setCampaign(on ? "__all__" : c.campaign)}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "1fr auto auto",
                            gap: 10,
                            alignItems: "center",
                            fontSize: 12.5,
                            textAlign: "left",
                            padding: "7px 8px",
                            borderRadius: 6,
                            cursor: "pointer",
                            border: `1px solid ${on ? "var(--volt-border)" : "transparent"}`,
                            background: on ? "var(--volt-bg)" : "transparent",
                            color: "var(--silver)",
                          }}
                        >
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {c.campaign === "(none)" ? t("dash.insights.campaign.none") : c.campaign}
                          </span>
                          <span style={{ color: "var(--fg3)", fontVariantNumeric: "tabular-nums" }}>
                            {c.starts}→{c.confirmed}
                          </span>
                          <span style={{ color: "var(--volt)", fontWeight: 600, width: 42, textAlign: "right" }}>
                            {conv}%
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </Panel>

            <Panel title={t("dash.insights.topPages")}>
              {data.top_pages.length === 0 ? (
                <Empty text={t("dash.insights.nodata")} />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                  {data.top_pages.map((p) => (
                    <div key={p.path} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                      <span style={{ color: "var(--silver)", flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={p.path}>{p.path}</span>
                      <span style={{ color: "var(--fg3)", fontSize: 12 }}>{msText(p.avg_ms)}</span>
                      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--arctic)", width: 40, textAlign: "right" }}>{p.views}</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title={t("dash.insights.sources")}>
              <BarList rows={[...rowsOf(data.utm_sources, "—"), ...rowsOf(data.referrers, t("dash.insights.direct"))]} empty={t("dash.insights.nodata")} />
            </Panel>

            <Panel title={t("dash.insights.devices")}>
              <Donut data={rowsOf(data.devices, "—")} />
              <div style={{ height: 14 }} />
              <div style={{ height: 14 }} />
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>{t("dash.insights.countries")}</div>
              <BarList rows={rowsOf(data.countries, "—")} empty={t("dash.insights.nodata")} />
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
