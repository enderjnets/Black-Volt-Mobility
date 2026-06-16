"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";
import { useViewport } from "@/lib/useViewport";
import { openMapsTo } from "@/lib/maps";
import { listRides } from "@/lib/booking";
import { getDashboardStats, getWeek, type DashStats, type WeekEarnings } from "@/lib/dashboard";
import { StatusPill } from "./DashShell";
import { type Ride } from "./data";
import { apiToUiRide, fmtWhen, isToday } from "./status";
import { RideDetail } from "./RideDetail";

const fmtMoney = (n: number) =>
  Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`;

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

export function RideRow({ r, onOpen }: { r: Ride; onOpen?: (rid: number) => void }) {
  const { t } = useI18n();
  const [h, setH] = useState(false);
  const { compact } = useViewport();
  const click = r.rid != null && onOpen ? () => onOpen(r.rid!) : undefined;
  // Quick "navigate to pickup" launcher — only for rides the driver still needs
  // to drive to (upcoming / active) and that actually have a pickup address.
  const canNavigate = (r.status === "upcoming" || r.status === "active") && !!r.from;
  const navigate = (e: React.MouseEvent) => {
    e.stopPropagation();
    openMapsTo(r.from);
  };

  if (compact) {
    return (
      <div
        onClick={click}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "13px 14px",
          margin: "0 6px 8px",
          background: "var(--obsidian-2)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          cursor: click ? "pointer" : "default",
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
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
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
            <StatusPill status={r.overdue ? "overdue" : r.status} />
            {r.flight && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--silver)" }}>
                <Icon name="plane" size={11} color="var(--volt)" />
                {r.flight}
              </span>
            )}
            {canNavigate && (
              <button
                type="button"
                onClick={navigate}
                aria-label={t("dash.ride.navigate")}
                title={t("dash.ride.navigate")}
                style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: "var(--radius-full)", background: "var(--volt-bg)", border: "1px solid var(--volt-border)", color: "var(--volt)", cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: "var(--font-sans)", flexShrink: 0 }}
              >
                <Icon name="navigation" size={12} color="var(--volt)" />
                {t("dash.ride.nav")}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={click}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(150px, 1.2fr) minmax(0, 1.4fr) 100px 60px 104px 36px",
        alignItems: "center",
        gap: 12,
        padding: "13px 16px",
        borderRadius: "var(--radius-md)",
        background: h ? "var(--obsidian-2)" : "transparent",
        transition: "background .12s",
        cursor: click ? "pointer" : "default",
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
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {r.client}
          </div>
          <div style={{ fontSize: 11, color: "var(--fg3)" }}>{r.time}</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--silver)", minWidth: 0, overflow: "hidden" }}>
        <Icon name="circle-dot" size={14} color="var(--volt)" />
        <span style={{ whiteSpace: "nowrap", flexShrink: 1, overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{r.from}</span>
        <Icon name="arrow-right" size={13} color="var(--fg3)" />
        <span style={{ whiteSpace: "nowrap", flexShrink: 1, overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{r.to}</span>
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
      <StatusPill status={r.overdue ? "overdue" : r.status} />
      <div style={{ display: "flex", justifyContent: "center" }}>
        {canNavigate && (
          <button
            type="button"
            onClick={navigate}
            aria-label={t("dash.ride.navigate")}
            title={t("dash.ride.navigate")}
            style={{ width: 30, height: 30, borderRadius: 8, background: "var(--volt-bg)", border: "1px solid var(--volt-border)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0 }}
          >
            <Icon name="navigation" size={15} color="var(--volt)" />
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ icon, text }: { icon: string; text: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "40px 20px", textAlign: "center" }}>
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 12,
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon name={icon} size={22} color="var(--fg3)" />
      </div>
      <span style={{ fontSize: 13.5, color: "var(--fg3)", fontFamily: "var(--font-sans)" }}>{text}</span>
    </div>
  );
}

// Weekly earnings, Monday→Sunday. The current day (today) is highlighted; bars
// are scaled by revenue and labelled with each day's initial.
function MiniBars({ data }: { data: { day: string; date: string; revenue: number }[] }) {
  const today = new Date().toDateString();
  const max = Math.max(...data.map((d) => d.revenue), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 90 }}>
      {data.map((d, i) => {
        const isCurrent = new Date(`${d.date}T00:00`).toDateString() === today;
        return (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
            <div
              title={fmtMoney(d.revenue)}
              style={{
                width: "100%",
                height: `${Math.max(2, (d.revenue / max) * 70)}px`,
                borderRadius: 4,
                background: isCurrent ? "var(--volt)" : "var(--obsidian-3)",
                boxShadow: isCurrent ? "var(--shadow-volt-sm)" : "none",
              }}
            />
            <span style={{ fontSize: 11, color: isCurrent ? "var(--volt)" : "var(--fg3)" }}>{d.day[0]}</span>
          </div>
        );
      })}
    </div>
  );
}

// Monday (local) of the week containing `d`.
function mondayOf(d: Date): Date {
  const x = new Date(d);
  const wd = (x.getDay() + 6) % 7; // 0 = Monday
  x.setDate(x.getDate() - wd);
  x.setHours(0, 0, 0, 0);
  return x;
}

// "Jun 15 – 21" (same month) or "Jun 29 – Jul 5" (cross-month) for a week offset
// (0 = this week, negative = past), formatted in the active locale.
function weekRange(offset: number, locale: string): string {
  const mon = mondayOf(new Date());
  mon.setDate(mon.getDate() + offset * 7);
  const sun = new Date(mon);
  sun.setDate(sun.getDate() + 6);
  const md = (d: Date) => d.toLocaleDateString(locale, { month: "short", day: "numeric" });
  return mon.getMonth() === sun.getMonth() ? `${md(mon)} – ${sun.getDate()}` : `${md(mon)} – ${md(sun)}`;
}

const WEEK_MIN_OFFSET = -260; // ~5 years back (matches the backend bound)
const WEEK_OPTIONS = 12; // weeks listed in the dropdown

// "This week" card with a week navigator: ‹ › arrows + a date-range dropdown to
// jump to any recent week (Uber-style). Mobile-first: the dropdown is a bottom
// sheet on phones (never clipped by the fixed tab bar) and a popover on larger
// screens. The bars keep the Black Volt style; the selected week's total + range
// update on navigation.
function WeekChart() {
  const { t, locale } = useI18n();
  const { phone } = useViewport();
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<WeekEarnings | null>(null);
  const [open, setOpen] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    getWeek(offset)
      .then((d) => alive && setData(d))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [offset]);

  // Close the popover on outside click / Escape (desktop). The phone sheet has
  // its own backdrop.
  useEffect(() => {
    if (!open || phone) return;
    const onDoc = (e: MouseEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, phone]);

  const total = data?.total ?? 0;
  const subKey = offset === 0 ? "dash.week.thisWeek" : offset === -1 ? "dash.week.lastWeek" : null;

  const arrow = (dir: "prev" | "next", disabled: boolean, onClick: () => void) => (
    <button
      type="button"
      aria-label={t(dir === "prev" ? "dash.week.prev" : "dash.week.next")}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{
        width: 44,
        height: 44,
        minWidth: 44,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--line-strong)",
        background: "var(--obsidian-2)",
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.35 : 1,
        WebkitTapHighlightColor: "transparent",
      }}
    >
      <Icon name={dir === "prev" ? "chevron-left" : "chevron-right"} size={18} color="var(--silver)" />
    </button>
  );

  const optionRows = Array.from({ length: WEEK_OPTIONS }, (_, i) => -i).map((o) => {
    const active = o === offset;
    const sk = o === 0 ? t("dash.week.thisWeek") : o === -1 ? t("dash.week.lastWeek") : "";
    return (
      <button
        key={o}
        type="button"
        role="option"
        aria-selected={active}
        onClick={() => {
          setOffset(o);
          setOpen(false);
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: "100%",
          minHeight: 44,
          padding: "10px 12px",
          border: "none",
          borderRadius: "var(--radius-md)",
          background: active ? "var(--volt-bg)" : "transparent",
          color: active ? "var(--volt)" : "var(--arctic)",
          boxShadow: active ? "inset 0 0 0 1px var(--volt-border)" : "none",
          cursor: "pointer",
          fontFamily: "var(--font-sans)",
          fontSize: 14,
          fontWeight: active ? 700 : 500,
          textAlign: "left",
          WebkitTapHighlightColor: "transparent",
        }}
      >
        <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {weekRange(o, locale)}
        </span>
        {sk && <span style={{ fontSize: 11.5, color: active ? "var(--volt)" : "var(--fg3)" }}>{sk}</span>}
      </button>
    );
  });

  return (
    <div
      ref={cardRef}
      style={{
        background: "var(--obsidian)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-lg)",
        padding: 18,
        position: "relative",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12, gap: 8 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{t("dash.week")}</span>
        <span style={{ fontSize: 12, color: "var(--fg3)" }}>
          {t("dash.week.total")}{" "}
          <strong style={{ fontFamily: "var(--font-display)", color: "var(--volt)" }}>{fmtMoney(total)}</strong>
        </span>
      </div>

      {/* Navigator: ‹ [date-range dropdown] › */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        {arrow("prev", offset <= WEEK_MIN_OFFSET, () => setOffset((o) => Math.max(WEEK_MIN_OFFSET, o - 1)))}
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={t("dash.week.pick")}
          onClick={() => setOpen((v) => !v)}
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 44,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
            padding: "0 10px",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--line-strong)",
            background: "var(--obsidian-2)",
            cursor: "pointer",
            color: "var(--arctic)",
            fontFamily: "var(--font-sans)",
            fontSize: 13.5,
            fontWeight: 600,
            WebkitTapHighlightColor: "transparent",
          }}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{weekRange(offset, locale)}</span>
          {subKey && <span style={{ fontSize: 11, color: "var(--fg3)", flexShrink: 0 }}>· {t(subKey)}</span>}
          <Icon name="chevron-down" size={15} color="var(--silver)" />
        </button>
        {arrow("next", offset >= 0, () => setOffset((o) => Math.min(0, o + 1)))}
      </div>

      {/* Desktop/tablet popover */}
      {open && !phone && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            left: 18,
            right: 18,
            top: 96,
            zIndex: 50,
            background: "var(--obsidian-2)",
            border: "1px solid var(--volt-border)",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--shadow-pop)",
            maxHeight: 280,
            overflowY: "auto",
            padding: 6,
            display: "flex",
            flexDirection: "column",
            gap: 2,
          }}
        >
          {optionRows}
        </div>
      )}

      {/* Phone bottom sheet — above the fixed tab bar, never clipped */}
      {open && phone && (
        <div
          onClick={() => setOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(5,5,9,0.6)", backdropFilter: "blur(3px)", display: "flex", alignItems: "flex-end" }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%",
              background: "var(--obsidian)",
              borderTop: "1px solid var(--volt-border)",
              borderTopLeftRadius: 18,
              borderTopRightRadius: 18,
              padding: "10px 14px calc(18px + env(safe-area-inset-bottom))",
              boxShadow: "var(--shadow-pop)",
              maxHeight: "70vh",
              overflowY: "auto",
            }}
          >
            <div style={{ width: 38, height: 4, borderRadius: 99, background: "var(--line-strong)", margin: "0 auto 12px" }} />
            <div style={{ fontSize: 12, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.08em", margin: "0 4px 8px" }}>
              {t("dash.week.pick")}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>{optionRows}</div>
          </div>
        </div>
      )}

      {data && total > 0 ? <MiniBars data={data.days} /> : <EmptyState icon="trending-up" text={t("dash.empty.week")} />}
    </div>
  );
}

// Compact "time until" the next pickup: "5d 2h", "2h 30m", "12m", or `now`.
function fmtCountdown(iso: string | null | undefined, now: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const mins = Math.floor((d.getTime() - Date.now()) / 60000);
  if (mins <= 0) return now;
  const days = Math.floor(mins / 1440);
  const hrs = Math.floor((mins % 1440) / 60);
  const m = mins % 60;
  if (days > 0) return `${days}d ${hrs}h`;
  if (hrs > 0) return `${hrs}h ${m}m`;
  return `${m}m`;
}

export function Overview() {
  const { t } = useI18n();
  const [stats, setStats] = useState<DashStats | null>(null);
  const nextAt = stats?.next_pickup?.at;
  const [today, setToday] = useState<Ride[]>([]);
  const [upcomingMode, setUpcomingMode] = useState(false);
  const [detail, setDetail] = useState<number | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    getDashboardStats().then((s) => alive && setStats(s)).catch(() => {});
    listRides()
      .then((rides) => {
        if (!alive) return;
        const todays = rides.filter((r) => isToday(r.scheduled_at));
        // With rides today, show the whole day. With none, fall back to the next
        // upcoming rides (future + still open) — never the old completed ones.
        const upcoming = todays.length === 0;
        const now = Date.now();
        const source = upcoming
          ? rides.filter(
              (r) =>
                r.scheduled_at != null &&
                new Date(r.scheduled_at).getTime() > now &&
                !["completed", "cancelled", "no_show"].includes(r.status),
            )
          : todays;
        setUpcomingMode(upcoming);
        setToday(source.slice(0, 6).map(apiToUiRide));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [reload]);

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="bv-kpi-row" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <KpiCard icon="navigation" label={t("dash.kpi.rides")} value={String(stats?.today.rides ?? 0)} />
        <KpiCard icon="dollar-sign" label={t("dash.kpi.revenue")} value={fmtMoney(stats?.today.revenue ?? 0)} accent />
        <KpiCard icon="star" label={t("dash.kpi.rating")} value="4.98" />
        <KpiCard
          icon="clock"
          label={t("dash.kpi.next")}
          value={nextAt ? fmtCountdown(nextAt, t("dash.next.now")) : "—"}
          sub={nextAt ? `${fmtWhen(nextAt)}${stats?.next_pickup?.client ? ` · ${stats.next_pickup.client}` : ""}` : undefined}
        />
      </div>

      <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1.7fr 1fr", gap: 20, alignItems: "start" }}>
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: "6px 6px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px 8px" }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--arctic)" }}>{t(upcomingMode ? "dash.upcomingRides" : "dash.today")}</span>
          </div>
          {today.length === 0 ? (
            <EmptyState icon="navigation" text={t("dash.empty.rides")} />
          ) : (
            today.map((r) => <RideRow key={r.id} r={r} onOpen={setDetail} />)
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 18, boxShadow: "var(--shadow-volt)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <Icon name="sparkles" size={16} color="var(--volt)" />
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{t("dash.ai")}</span>
            </div>
            <p style={{ fontSize: 13, color: "var(--silver)", lineHeight: 1.55, margin: 0 }}>
              {stats
                ? t("dash.ai.summary", {
                    rides: stats.today.rides,
                    upcoming: stats.today.upcoming,
                    clients: stats.totals.clients,
                  })
                : t("common.loading")}
            </p>
          </div>
          <WeekChart />
        </div>
      </div>

      {detail != null && (
        <RideDetail
          rideId={detail}
          onClose={() => setDetail(null)}
          onChanged={() => {
            setReload((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}
