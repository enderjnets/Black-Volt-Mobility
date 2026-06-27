"use client";

/* Driver Insights — first-party usage analytics. Reads /api/v1/analytics/summary
   and renders KPIs, a pageviews timeseries, the booking funnel, top pages, and
   source/device/country breakdowns. Styled to match Overview. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
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

function Timeseries({ data }: { data: { day: string; pageviews: number }[] }) {
  const { t } = useI18n();
  if (!data.length) return <Empty text={t("dash.insights.nodata")} />;
  const max = Math.max(...data.map((d) => d.pageviews), 1);
  const show = data.slice(-30);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 110 }}>
      {show.map((d, i) => (
        <div key={d.day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, minWidth: 0 }} title={`${d.day}: ${d.pageviews}`}>
          <div
            style={{
              width: "100%",
              height: `${Math.max(2, (d.pageviews / max) * 88)}px`,
              borderRadius: 3,
              background: i === show.length - 1 ? "var(--volt)" : "var(--obsidian-3)",
              boxShadow: i === show.length - 1 ? "var(--shadow-volt-sm)" : "none",
            }}
          />
        </div>
      ))}
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
    { key: "book_start", label: t("dash.insights.f.start") },
    { key: "book_review", label: t("dash.insights.f.review") },
    { key: "book_pay", label: t("dash.insights.f.pay") },
    { key: "book_confirmed", label: t("dash.insights.f.confirmed") },
  ];
  const fStart = f["book_start"] || 0;

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

          <Panel title={t("dash.insights.pageviewsOverTime")}>
            <Timeseries data={data.timeseries} />
          </Panel>

          <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "start" }}>
            <Panel title={t("dash.insights.funnel")}>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {funnelSteps.map((s) => {
                  const v = f[s.key] || 0;
                  const pct = fStart ? Math.round((v / fStart) * 100) : 0;
                  return (
                    <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Icon name="circle-dot" size={13} color="var(--volt)" />
                      <span style={{ fontSize: 13, color: "var(--silver)", flex: 1 }}>{s.label}</span>
                      <div style={{ width: 110, height: 8, borderRadius: 99, background: "var(--obsidian-3)", overflow: "hidden" }}>
                        <div style={{ width: `${pct}%`, height: "100%", background: "var(--volt)", borderRadius: 99 }} />
                      </div>
                      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 14, color: "var(--arctic)", width: 30, textAlign: "right" }}>{v}</span>
                    </div>
                  );
                })}
                <div style={{ borderTop: "1px solid var(--line)", marginTop: 4, paddingTop: 10, fontSize: 12.5, color: "var(--fg3)", display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon name="message-circle" size={13} color="var(--success)" />
                  {t("dash.insights.signins", { n: f["sign_in"] || 0 })}
                </div>
                {(f["book_pay_failed"] || 0) > 0 && (
                  <div style={{ fontSize: 12.5, color: "var(--danger)", display: "flex", alignItems: "center", gap: 6 }}>
                    <Icon name="alert-circle" size={13} color="var(--danger)" />
                    {t("dash.insights.payfailed", { n: f["book_pay_failed"] || 0 })}
                  </div>
                )}
              </div>
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
              <BarList rows={rowsOf(data.devices, "—")} empty={t("dash.insights.nodata")} />
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
