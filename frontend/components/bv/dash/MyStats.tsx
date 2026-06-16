"use client";

/* My Stats — the driver's own growth dashboard. The business runs on converting
   Uber/Lyft riders into private clients, so this tab tracks that sales funnel
   (conversations → pitches → contacts → clients → revenue), shows smoothed
   conversion rates with a confidence band, projects forward at the current pace,
   and gives a goal calculator: "to make $X, talk to N people a day." The top of
   the funnel is logged by hand each day; the bottom is real Client/Ride data.
   Charts are hand-rolled to match Overview/Insights (no chart library). */

import { useCallback, useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { PlatformIncome } from "./PlatformIncome";
import { useI18n } from "@/lib/i18n";
import {
  type FunnelRate,
  type FunnelSummary,
  type ProjectResult,
  getFunnelSummary,
  projectGoal,
  saveFunnelLog,
  setFunnelGoal,
} from "@/lib/funnel";

const RANGES = [7, 30, 90];

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}
function money(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}
function num(n: number, d = 0): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: d });
}

// ── Shared bits (match Insights/Overview styling) ────────────────────────────
function Kpi({
  icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: string;
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
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
      {sub && <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 8 }}>{sub}</div>}
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon?: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        {icon && <Icon name={icon} size={16} color="var(--volt)" />}
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div style={{ fontSize: 13, color: "var(--fg3)", padding: "8px 0" }}>{text}</div>;
}

// Small number input for the quick-log.
function NumIn({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label style={{ flex: 1, minWidth: 92, display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 12.5, color: "var(--silver)", fontWeight: 600 }}>{label}</span>
      <input
        type="number"
        min={0}
        inputMode="numeric"
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
        style={{
          width: "100%",
          background: "var(--obsidian-2)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: "11px 12px",
          color: "var(--arctic)",
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 20,
          fontVariantNumeric: "tabular-nums",
        }}
      />
      <span style={{ fontSize: 11.5, color: "var(--fg3)" }}>{hint}</span>
    </label>
  );
}

// Funnel stage bar (width proportional to the top of the funnel).
function StageBar({ label, value, max, tone }: { label: string; value: number; max: number; tone: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ fontSize: 13, color: "var(--silver)", width: 130, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 26, borderRadius: 6, background: "var(--obsidian-3)", overflow: "hidden", position: "relative" }}>
        <div
          style={{
            width: `${max > 0 ? Math.max(value > 0 ? 4 : 0, (value / max) * 100) : 0}%`,
            height: "100%",
            background: tone,
            borderRadius: 6,
            transition: "width .3s",
          }}
        />
      </div>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)", width: 44, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {num(value)}
      </span>
    </div>
  );
}

function RateRow({ label, rate, t }: { label: string; rate: FunnelRate; t: (k: string) => string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ fontSize: 13, color: "var(--silver)", flex: 1 }}>{label}</span>
      {rate.low_data && (
        <span title={t("dash.stats.lowDataHint")} style={{ fontSize: 11, color: "var(--warning)", display: "flex", alignItems: "center", gap: 4 }}>
          <Icon name="circle-dot" size={12} color="var(--warning)" />
          {t("dash.stats.lowData")}
        </span>
      )}
      <span style={{ fontSize: 11.5, color: "var(--fg3)" }}>
        {pct(rate.low)}–{pct(rate.high)}
      </span>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--volt)", width: 52, textAlign: "right" }}>
        {pct(rate.point)}
      </span>
    </div>
  );
}

// Conversations timeseries (volt bars, last entry highlighted).
function Trend({ data, accessor, fmt }: { data: { day: string; date: string }[] & Record<string, unknown>[]; accessor: (d: Record<string, unknown>) => number; fmt: (n: number) => string }) {
  const vals = data.map(accessor);
  const max = Math.max(...vals, 1);
  const show = data.slice(-30);
  const base = data.length - show.length;
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 96 }}>
      {show.map((d, i) => {
        const v = accessor(d);
        const last = base + i === data.length - 1;
        return (
          <div key={String(d.date)} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", minWidth: 0 }} title={`${String(d.date)}: ${fmt(v)}`}>
            <div
              style={{
                width: "100%",
                height: `${Math.max(2, (v / max) * 88)}px`,
                borderRadius: 3,
                background: last ? "var(--volt)" : "var(--obsidian-3)",
                boxShadow: last ? "var(--shadow-volt-sm)" : "none",
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

// ── Quick-log card ───────────────────────────────────────────────────────────
function QuickLog({ summary, onSaved }: { summary: FunnelSummary; onSaved: () => void }) {
  const { t } = useI18n();
  const tl = summary.today_log;
  const [conv, setConv] = useState(tl?.conversations ?? 0);
  const [pit, setPit] = useState(tl?.pitches ?? 0);
  const [con, setCon] = useState(tl?.contacts ?? 0);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setConv(tl?.conversations ?? 0);
    setPit(tl?.pitches ?? 0);
    setCon(tl?.contacts ?? 0);
  }, [tl?.conversations, tl?.pitches, tl?.contacts]);

  const save = async () => {
    setBusy(true);
    try {
      await saveFunnelLog({ conversations: conv, pitches: pit, contacts: con });
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
      onSaved();
    } catch {
      /* surfaced by reload */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 18, boxShadow: "var(--shadow-volt-sm)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4, flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="zap" size={16} color="var(--volt)" />
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{t("dash.stats.logToday")}</span>
        </div>
        {summary.streak > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, color: "var(--volt)", fontWeight: 600 }}>
            <Icon name="flame" size={15} color="var(--volt)" />
            {t("dash.stats.streak", { n: summary.streak })}
          </span>
        )}
      </div>
      <div style={{ fontSize: 12.5, color: "var(--fg3)", marginBottom: 14 }}>{t("dash.stats.logHint")}</div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <NumIn label={t("dash.stats.f.conversations")} hint={t("dash.stats.f.conversationsHint")} value={conv} onChange={setConv} />
        <NumIn label={t("dash.stats.f.pitches")} hint={t("dash.stats.f.pitchesHint")} value={pit} onChange={setPit} />
        <NumIn label={t("dash.stats.f.contacts")} hint={t("dash.stats.f.contactsHint")} value={con} onChange={setCon} />
        <Button variant="solid" icon={saved ? "check" : "zap"} disabled={busy} onClick={save}>
          {saved ? t("dash.stats.saved") : busy ? t("dash.stats.saving") : t("dash.stats.save")}
        </Button>
      </div>
    </div>
  );
}

// ── Goal calculator ──────────────────────────────────────────────────────────
function GoalCalculator({ summary, onGoalSaved }: { summary: FunnelSummary; onGoalSaved: () => void }) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"revenue" | "clients">("revenue");
  const [period, setPeriod] = useState<"week" | "month" | "year">("week");
  const [amount, setAmount] = useState<number>(
    summary.goal.target_weekly_revenue ?? 2000,
  );
  const [workDays, setWorkDays] = useState<number>(summary.goal.working_days_per_week);
  const [result, setResult] = useState<ProjectResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedGoal, setSavedGoal] = useState(false);

  const compute = useCallback(async () => {
    setBusy(true);
    try {
      const body =
        mode === "revenue"
          ? { period, target_revenue: amount }
          : { period, target_clients: amount };
      setResult(await projectGoal(body));
    } catch {
      setResult(null);
    } finally {
      setBusy(false);
    }
  }, [mode, period, amount]);

  // Auto-compute on first load and whenever inputs change.
  useEffect(() => {
    compute();
  }, [compute]);

  const saveGoal = async () => {
    try {
      await setFunnelGoal({
        target_weekly_revenue: mode === "revenue" && period === "week" ? amount : summary.goal.target_weekly_revenue,
        target_monthly_clients: mode === "clients" && period === "month" ? amount : summary.goal.target_monthly_clients,
        working_days_per_week: workDays,
      });
      setSavedGoal(true);
      setTimeout(() => setSavedGoal(false), 1800);
      onGoalSaved();
    } catch {
      /* ignore */
    }
  };

  const Seg = ({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) => (
    <button
      onClick={onClick}
      style={{
        padding: "7px 14px",
        borderRadius: "var(--radius-full)",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 600,
        border: "none",
        fontFamily: "var(--font-sans)",
        background: active ? "var(--volt-bg-20)" : "transparent",
        color: active ? "var(--volt)" : "var(--silver)",
        boxShadow: active ? "inset 0 0 0 1px var(--volt-border)" : "none",
      }}
    >
      {children}
    </button>
  );

  const req = result?.required;

  return (
    <Panel title={t("dash.stats.calc.title")} icon="calculator">
      <div style={{ fontSize: 12.5, color: "var(--fg3)", marginBottom: 14 }}>{t("dash.stats.calc.hint")}</div>

      {/* mode + period + amount */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 4, background: "var(--obsidian-2)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 4 }}>
          <Seg active={mode === "revenue"} onClick={() => setMode("revenue")}>{t("dash.stats.calc.money")}</Seg>
          <Seg active={mode === "clients"} onClick={() => setMode("clients")}>{t("dash.stats.calc.clients")}</Seg>
        </div>
        <div style={{ display: "flex", gap: 4, background: "var(--obsidian-2)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 4 }}>
          <Seg active={period === "week"} onClick={() => setPeriod("week")}>{t("dash.stats.calc.week")}</Seg>
          <Seg active={period === "month"} onClick={() => setPeriod("month")}>{t("dash.stats.calc.month")}</Seg>
          <Seg active={period === "year"} onClick={() => setPeriod("year")}>{t("dash.stats.calc.year")}</Seg>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
        <label style={{ flex: 2, minWidth: 160, display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 12.5, color: "var(--silver)", fontWeight: 600 }}>
            {mode === "revenue" ? t("dash.stats.calc.targetMoney") : t("dash.stats.calc.targetClients")}
          </span>
          <input
            type="number"
            min={0}
            value={amount}
            onChange={(e) => setAmount(Math.max(0, Number(e.target.value) || 0))}
            style={{
              width: "100%",
              background: "var(--obsidian-2)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-md)",
              padding: "11px 12px",
              color: "var(--arctic)",
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 20,
            }}
          />
        </label>
        <label style={{ flex: 1, minWidth: 110, display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 12.5, color: "var(--silver)", fontWeight: 600 }}>{t("dash.stats.calc.workDays")}</span>
          <input
            type="number"
            min={1}
            max={7}
            value={workDays}
            onChange={(e) => setWorkDays(Math.min(7, Math.max(1, Number(e.target.value) || 1)))}
            style={{
              width: "100%",
              background: "var(--obsidian-2)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-md)",
              padding: "11px 12px",
              color: "var(--arctic)",
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 20,
            }}
          />
        </label>
      </div>

      {/* result */}
      {busy && !result && <Empty text={t("common.loading")} />}
      {result && !result.ok && result.revenue_unknown && (
        <div style={{ fontSize: 13, color: "var(--warning)", display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="circle-dot" size={14} color="var(--warning)" />
          {t("dash.stats.calc.noEarnings")}
        </div>
      )}
      {result && result.ok && req && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* the headline number */}
          <div style={{ background: "var(--volt-bg)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-md)", padding: 16, textAlign: "center" }}>
            <div style={{ fontSize: 12.5, color: "var(--silver)", marginBottom: 6 }}>{t("dash.stats.calc.yourNumber")}</div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 38, color: "var(--volt)", lineHeight: 1 }}>
              {num(Math.ceil(req.conversations_per_day))}
            </div>
            <div style={{ fontSize: 13, color: "var(--arctic)", marginTop: 6 }}>{t("dash.stats.calc.perDay")}</div>
            <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 4 }}>
              {t("dash.stats.calc.range", {
                lo: num(Math.ceil(req.conversations_per_day_low)),
                hi: num(Math.ceil(req.conversations_per_day_high)),
              })}
            </div>
          </div>
          {/* breakdown */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 13, color: "var(--silver)" }}>
            <span>{t("dash.stats.calc.breakdown", {
              clients: num(result.target_clients ?? 0, 1),
              contacts: num(Math.ceil(req.contacts)),
              pitches: num(Math.ceil(req.pitches)),
              conversations: num(Math.ceil(req.conversations)),
            })}</span>
          </div>
          {result.rates?.low_data && (
            <div style={{ fontSize: 12, color: "var(--warning)", display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="circle-dot" size={12} color="var(--warning)" />
              {t("dash.stats.calc.lowData")}
            </div>
          )}
          <div>
            <Button variant="tint" icon={savedGoal ? "check" : "target"} onClick={saveGoal}>
              {savedGoal ? t("dash.stats.saved") : t("dash.stats.calc.saveGoal")}
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────
export function MyStats() {
  const { t } = useI18n();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<FunnelSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setErr(false);
    return getFunnelSummary(days)
      .then(setData)
      .catch(() => setErr(true))
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const stageMax = data ? Math.max(data.totals.conversations, 1) : 1;

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.stats.subtitle")}</span>
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
              {t("dash.stats.days", { n: r })}
            </button>
          ))}
        </div>
      </div>

      {err && <Empty text={t("dash.stats.error")} />}
      {loading && !data && <Empty text={t("common.loading")} />}

      {data && (
        <>
          <QuickLog summary={data} onSaved={load} />

          {/* This-week KPIs vs goal */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Kpi icon="flame" label={t("dash.stats.kpi.streak")} value={num(data.streak)} sub={t("dash.stats.kpi.streakSub")} accent />
            <Kpi icon="message-circle" label={t("dash.stats.kpi.weekConv")} value={num(data.week.conversations)} />
            <Kpi
              icon="users"
              label={t("dash.stats.kpi.weekClients")}
              value={num(data.week.clients)}
              sub={data.goal.target_monthly_clients ? t("dash.stats.kpi.goalClients", { n: data.goal.target_monthly_clients }) : undefined}
            />
            <Kpi
              icon="dollar-sign"
              label={t("dash.stats.kpi.weekRevenue")}
              value={money(data.week.revenue)}
              sub={data.goal.target_weekly_revenue ? t("dash.stats.kpi.goalRevenue", { n: money(data.goal.target_weekly_revenue) }) : undefined}
            />
          </div>

          <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "start" }}>
            {/* Funnel */}
            <Panel title={t("dash.stats.funnel.title")} icon="bar-chart-3">
              {data.totals.conversations === 0 && data.totals.clients === 0 ? (
                <Empty text={t("dash.stats.funnel.empty")} />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                  <StageBar label={t("dash.stats.f.conversations")} value={data.totals.conversations} max={stageMax} tone="var(--volt)" />
                  <StageBar label={t("dash.stats.f.pitches")} value={data.totals.pitches} max={stageMax} tone="var(--volt)" />
                  <StageBar label={t("dash.stats.f.contacts")} value={data.totals.contacts} max={stageMax} tone="var(--volt)" />
                  <StageBar label={t("dash.stats.f.clients")} value={data.totals.clients} max={stageMax} tone="var(--success)" />
                  <div style={{ borderTop: "1px solid var(--line)", marginTop: 4, paddingTop: 10, fontSize: 12.5, color: "var(--fg3)" }}>
                    {t("dash.stats.funnel.overall", { p: pct(data.rates.overall_point) })}
                  </div>
                </div>
              )}
            </Panel>

            {/* Conversion rates */}
            <Panel title={t("dash.stats.rates.title")} icon="trending-up">
              <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
                <RateRow label={t("dash.stats.rates.pitch")} rate={data.rates.pitch} t={t} />
                <RateRow label={t("dash.stats.rates.contact")} rate={data.rates.contact} t={t} />
                <RateRow label={t("dash.stats.rates.convert")} rate={data.rates.convert} t={t} />
                <div style={{ borderTop: "1px solid var(--line)", marginTop: 4, paddingTop: 10, fontSize: 12, color: "var(--fg3)" }}>
                  {t("dash.stats.rates.note")}
                </div>
              </div>
            </Panel>

            {/* Trend */}
            <Panel title={t("dash.stats.trend.conversations")} icon="message-circle">
              {data.totals.conversations === 0 ? (
                <Empty text={t("dash.stats.trend.empty")} />
              ) : (
                <Trend data={data.timeseries as never} accessor={(d) => Number(d.conversations)} fmt={(n) => num(n)} />
              )}
            </Panel>

            <Panel title={t("dash.stats.trend.revenue")} icon="dollar-sign">
              {data.totals.revenue === 0 ? (
                <Empty text={t("dash.stats.trend.emptyRev")} />
              ) : (
                <Trend data={data.timeseries as never} accessor={(d) => Number(d.revenue)} fmt={(n) => money(n)} />
              )}
            </Panel>
          </div>

          {/* Platform income (Uber/Lyft/Co-op screenshot import) */}
          <PlatformIncome days={days} />

          {/* Projection */}
          <Panel title={t("dash.stats.proj.title")} icon="trending-up">
            {data.totals.logged_days === 0 ? (
              <Empty text={t("dash.stats.proj.empty")} />
            ) : (
              <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontSize: 12.5, color: "var(--fg3)", marginBottom: 6 }}>{t("dash.stats.proj.pace", { n: num(data.projection.pace_per_day, 1) })}</div>
                  <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                    <div>
                      <div style={{ fontSize: 12, color: "var(--silver)", marginBottom: 4 }}>{t("dash.stats.proj.week")}</div>
                      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--arctic)" }}>
                        {num(data.projection.week.expected_clients, 1)} {t("dash.stats.proj.clients")}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--volt)" }}>{data.has_earnings ? money(data.projection.week.expected_revenue) : "—"}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 12, color: "var(--silver)", marginBottom: 4 }}>{t("dash.stats.proj.month")}</div>
                      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--arctic)" }}>
                        {num(data.projection.month.expected_clients, 1)} {t("dash.stats.proj.clients")}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--volt)" }}>{data.has_earnings ? money(data.projection.month.expected_revenue) : "—"}</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Panel>

          {/* Goal calculator */}
          <GoalCalculator summary={data} onGoalSaved={load} />
        </>
      )}
    </div>
  );
}
