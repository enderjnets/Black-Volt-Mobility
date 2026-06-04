"use client";

import { useEffect, useMemo, useState } from "react";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";
import { listRides } from "@/lib/booking";
import { CAL_STATUS, type CalRide } from "./data";
import { uiStatus } from "./status";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function key(y: number, m: number, d: number): string {
  return `${y}-${m}-${d}`;
}

function Chip({ ride, dense, onOpen }: { ride: CalRide; dense?: boolean; onOpen?: (rid: number) => void }) {
  return (
    <div
      onClick={ride.rid != null && onOpen ? () => onOpen(ride.rid!) : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: dense ? "2px 6px" : "4px 8px",
        borderRadius: 5,
        background: "var(--obsidian-3)",
        border: "1px solid var(--line-strong)",
        fontSize: dense ? 11 : 12,
        lineHeight: 1.2,
        overflow: "hidden",
        cursor: ride.rid != null && onOpen ? "pointer" : "default",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: CAL_STATUS[ride.s], flexShrink: 0 }} />
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--arctic)", flexShrink: 0 }}>{ride.t}</span>
      <span style={{ color: "var(--silver)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ride.c}</span>
    </div>
  );
}

function MonthView({
  y,
  m,
  byDate,
  today,
  onOpen,
}: {
  y: number;
  m: number;
  byDate: Map<string, CalRide[]>;
  today: { y: number; m: number; d: number };
  onOpen?: (rid: number) => void;
}) {
  const { t } = useI18n();
  const first = new Date(y, m, 1).getDay();
  const days = new Date(y, m + 1, 0).getDate();
  const cells: (number | null)[] = [];
  for (let i = 0; i < first; i++) cells.push(null);
  for (let d = 1; d <= days; d++) cells.push(d);
  while (cells.length % 7) cells.push(null);

  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
        {DOW.map((d) => (
          <div
            key={d}
            style={{
              padding: "10px 12px",
              fontSize: 11,
              color: "var(--fg3)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              borderBottom: "1px solid var(--line)",
              fontFamily: "var(--font-sans)",
            }}
          >
            {d}
          </div>
        ))}
        {cells.map((d, i) => {
          const rides = d ? byDate.get(key(y, m, d)) || [] : [];
          const isToday = d === today.d && m === today.m && y === today.y;
          return (
            <div
              key={i}
              style={{
                minHeight: 92,
                padding: 8,
                borderBottom: "1px solid var(--line)",
                borderRight: i % 7 !== 6 ? "1px solid var(--line)" : "none",
                background: isToday ? "var(--volt-bg)" : "transparent",
              }}
            >
              {d && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <span
                    style={{
                      fontFamily: "var(--font-display)",
                      fontWeight: 700,
                      fontSize: 13,
                      color: isToday ? "var(--void)" : "var(--silver)",
                      background: isToday ? "var(--volt)" : "transparent",
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      boxShadow: isToday ? "var(--shadow-volt-sm)" : "none",
                    }}
                  >
                    {d}
                  </span>
                  {rides.length > 0 && <span style={{ fontSize: 10, color: "var(--fg3)" }}>{rides.length}</span>}
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {rides.slice(0, 2).map((r, j) => (
                  <Chip key={j} ride={r} dense onOpen={onOpen} />
                ))}
                {rides.length > 2 && (
                  <span style={{ fontSize: 11, color: "var(--volt)", paddingLeft: 2 }}>{t("dash.cal.more", { n: rides.length - 2 })}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WeekView({
  byDate,
  today,
  onOpen,
}: {
  byDate: Map<string, CalRide[]>;
  today: { y: number; m: number; d: number };
  onOpen?: (rid: number) => void;
}) {
  // Week containing today (Sun→Sat).
  const base = new Date(today.y, today.m, today.d);
  const start = new Date(base);
  start.setDate(base.getDate() - base.getDay());
  const cols = Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(start);
    dt.setDate(start.getDate() + i);
    return dt;
  });

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 10 }}>
      {cols.map((dt) => {
        const rides = byDate.get(key(dt.getFullYear(), dt.getMonth(), dt.getDate())) || [];
        const isToday = dt.toDateString() === base.toDateString();
        return (
          <div
            key={dt.toISOString()}
            style={{
              background: "var(--obsidian)",
              border: `1px solid ${isToday ? "var(--volt-border)" : "var(--line-strong)"}`,
              borderRadius: "var(--radius-md)",
              padding: 10,
              minHeight: 320,
              boxShadow: isToday ? "var(--shadow-volt-sm)" : "none",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingBottom: 10, marginBottom: 10, borderBottom: "1px solid var(--line)" }}>
              <span style={{ fontSize: 10, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{DOW[dt.getDay()]}</span>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: isToday ? "var(--volt)" : "var(--arctic)" }}>{dt.getDate()}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {rides.length === 0 ? (
                <span style={{ fontSize: 11, color: "var(--fg3)", textAlign: "center", marginTop: 8 }}>—</span>
              ) : (
                rides.map((r, j) => (
                  <div
                    key={j}
                    onClick={r.rid != null && onOpen ? () => onOpen(r.rid!) : undefined}
                    style={{
                      padding: "7px 9px",
                      borderRadius: 7,
                      background: "var(--obsidian-3)",
                      border: "1px solid var(--line-strong)",
                      borderLeft: `3px solid ${CAL_STATUS[r.s]}`,
                      cursor: r.rid != null && onOpen ? "pointer" : "default",
                    }}
                  >
                    <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 13, color: "var(--arctic)" }}>{r.t}</div>
                    <div style={{ fontSize: 11.5, color: "var(--silver)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.c}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CalNav({ icon, onClick }: { icon: string; onClick: () => void }) {
  const [h, setH] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        width: 32,
        height: 32,
        borderRadius: 8,
        border: "1px solid var(--line-strong)",
        cursor: "pointer",
        background: h ? "var(--obsidian-2)" : "var(--obsidian)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Icon name={icon} size={16} color={h ? "var(--arctic)" : "var(--silver)"} />
    </button>
  );
}

export function Calendar({ onOpen }: { onOpen?: (rid: number) => void }) {
  const { t } = useI18n();
  const now = useMemo(() => new Date(), []);
  const today = { y: now.getFullYear(), m: now.getMonth(), d: now.getDate() };
  const [mode, setMode] = useState<"month" | "week">("month");
  const [view, setView] = useState({ y: today.y, m: today.m });
  const [byDate, setByDate] = useState<Map<string, CalRide[]>>(new Map());

  useEffect(() => {
    let alive = true;
    listRides()
      .then((rides) => {
        if (!alive) return;
        const map = new Map<string, CalRide[]>();
        for (const r of rides) {
          if (!r.scheduled_at) continue;
          // Cancelled / no-show rides don't belong on the calendar.
          if (uiStatus(r.status) === "cancelled") continue;
          const dt = new Date(r.scheduled_at);
          if (isNaN(dt.getTime())) continue;
          const k = key(dt.getFullYear(), dt.getMonth(), dt.getDate());
          const cr: CalRide = {
            t: dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }),
            c: r.client_name || r.passenger_name || "Guest",
            s: uiStatus(r.status),
            rid: r.id,
          };
          if (!map.has(k)) map.set(k, []);
          map.get(k)!.push(cr);
        }
        for (const list of map.values()) list.sort((a, b) => a.t.localeCompare(b.t));
        setByDate(map);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const shift = (n: number) =>
    setView((v) => {
      let m = v.m + n;
      let y = v.y;
      if (m < 0) {
        m = 11;
        y--;
      }
      if (m > 11) {
        m = 0;
        y++;
      }
      return { y, m };
    });

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--arctic)", minWidth: 150 }}>
            {MONTHS[view.m]} {view.y}
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            <CalNav icon="arrow-left" onClick={() => shift(-1)} />
            <CalNav icon="arrow-right" onClick={() => shift(1)} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginLeft: 8 }}>
            {(["upcoming", "active", "done"] as const).map((s) => (
              <span key={s} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--silver)" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: CAL_STATUS[s] }} />
                {t(`dash.status.${s}`)}
              </span>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", gap: 4, background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 3 }}>
          {(
            [
              ["month", t("dash.cal.month")],
              ["week", t("dash.cal.week")],
            ] as const
          ).map(([v, l]) => (
            <button
              key={v}
              onClick={() => setMode(v as "month" | "week")}
              style={{
                padding: "6px 16px",
                borderRadius: "var(--radius-full)",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                border: "none",
                fontFamily: "var(--font-sans)",
                background: mode === v ? "var(--volt-bg-20)" : "transparent",
                color: mode === v ? "var(--volt)" : "var(--silver)",
              }}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      {mode === "month" ? (
        <MonthView y={view.y} m={view.m} byDate={byDate} today={today} onOpen={onOpen} />
      ) : (
        <WeekView byDate={byDate} today={today} onOpen={onOpen} />
      )}
    </div>
  );
}
