"use client";

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";
import { useViewport } from "@/lib/useViewport";
import { openMapsTo } from "@/lib/maps";
import { listRides } from "@/lib/booking";
import { getDashboardStats, type DashStats } from "@/lib/dashboard";
import { StatusPill } from "./DashShell";
import { type Ride } from "./data";
import { apiToUiRide, fmtWhen, isToday } from "./status";
import { RideDetail } from "./RideDetail";

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

function MiniBars({ data }: { data: { day: string; rides: number }[] }) {
  const max = Math.max(...data.map((d) => d.rides), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 90 }}>
      {data.map((d, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: "100%",
              height: `${Math.max(2, (d.rides / max) * 70)}px`,
              borderRadius: 4,
              background: i === data.length - 1 ? "var(--volt)" : "var(--obsidian-3)",
              boxShadow: i === data.length - 1 ? "var(--shadow-volt-sm)" : "none",
            }}
          />
          <span style={{ fontSize: 11, color: "var(--fg3)" }}>{d.day[0]}</span>
        </div>
      ))}
    </div>
  );
}

function nextPickupShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function Overview() {
  const { t } = useI18n();
  const [stats, setStats] = useState<DashStats | null>(null);
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

  const week = stats?.week ?? [];

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="bv-kpi-row" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <KpiCard icon="navigation" label={t("dash.kpi.rides")} value={String(stats?.today.rides ?? 0)} sub={t("dash.kpi.ridesSub")} />
        <KpiCard icon="dollar-sign" label={t("dash.kpi.revenue")} value={`$${stats?.today.revenue ?? 0}`} sub={t("dash.kpi.revenueSub")} accent />
        <KpiCard icon="star" label={t("dash.kpi.rating")} value="4.98" />
        <KpiCard icon="clock" label={t("dash.kpi.next")} value={nextPickupShort(stats?.next_pickup?.at)} sub={stats?.next_pickup?.client || undefined} />
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
          <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)", marginBottom: 14 }}>{t("dash.week")}</div>
            {week.length ? <MiniBars data={week} /> : <EmptyState icon="trending-up" text={t("dash.empty.week")} />}
          </div>
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
