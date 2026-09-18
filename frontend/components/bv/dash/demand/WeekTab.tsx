"use client";

/* 7×24 planner per zone. Colour = expected Black offers; hatching = the estimate
   is still mostly the proxy prior (own_share < 0.2). Hand-rolled like the other
   dashboard charts — no chart library. */

import { useEffect, useMemo, useState } from "react";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import { DOW_KEYS, type WeekCell, type WeekPayload, getWeek } from "@/lib/demand";

const THIN = 0.2;

// private_rides carry tz-aware timestamps; bucket them into the Denver
// day-of-week/hour grid without ever touching the browser's own zone.
const DEN_CELL = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver", weekday: "short", hour: "numeric", hourCycle: "h23",
});
const DOW_INDEX: Record<string, number> = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

function shade(v: number, max: number): string {
  const x = max > 0 ? Math.min(1, v / max) : 0;
  // 0 → near-black, 1 → electric cyan.
  const a = 0.08 + 0.72 * x;
  return `rgba(0,229,255,${a.toFixed(3)})`;
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

// pct() rounds before display; a raw compare against THIN can disagree with
// what the rounded percent just showed (0.199 → "20%" but still < 0.2).
// Compare the same rounded value so the percent and the "thin" flag agree.
function isThin(share: number): boolean {
  return Math.round(share * 100) < THIN * 100;
}

export function WeekTab() {
  const { t } = useI18n();
  const [zone, setZone] = useState<string | null>(null);
  const [data, setData] = useState<WeekPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<{ d: number; h: number } | null>(null);

  useEffect(() => {
    let alive = true;
    setErr(null);
    getWeek(zone)
      .then((w) => alive && setData(w))
      .catch((e) => alive && setErr(String(e?.message || e)));
    return () => {
      alive = false;
    };
  }, [zone]);

  const max = useMemo(
    () => (data?.grid.length ? Math.max(...data.grid.flat().map((c) => c?.mean ?? 0)) : 0),
    [data],
  );
  const privateByCell = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.private_rides ?? []) {
      const parts = DEN_CELL.formatToParts(new Date(r.at));
      const weekday = parts.find((p) => p.type === "weekday")?.value;
      const hour = parts.find((p) => p.type === "hour")?.value;
      if (weekday === undefined || !(weekday in DOW_INDEX) || hour === undefined) continue;
      s.add(`${DOW_INDEX[weekday]}-${Number(hour)}`);
    }
    return s;
  }, [data]);

  if (err) return <div style={{ color: "#ff7a7a", fontSize: 13 }}>{t("dash.demand.week.err")}</div>;
  if (!data) return null;
  if (!data.grid.length) {
    return <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.week.empty")}</div>;
  }
  const cell: WeekCell | null = sel ? data.grid[sel.d][sel.h] : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* .bv-mobile-pad * { min-width: 0 } lets flex items shrink below their own
          nowrap text, so without flexShrink the chips overlap and a tap lands on
          the neighbour instead of scrolling. */}
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        {data.zones.map((z) => {
          const on = z.key === data.zone;
          return (
            <button
              key={z.key}
              onClick={() => setZone(z.key)}
              style={{ flexShrink: 0, whiteSpace: "nowrap", padding: "8px 12px", borderRadius: 999, border: `1px solid ${on ? "var(--volt)" : "var(--line-strong)"}`, background: on ? "rgba(0,229,255,0.12)" : "transparent", color: on ? "var(--volt)" : "var(--silver)", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              {z.name}
            </button>
          );
        })}
      </div>

      <div>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
          {t("dash.demand.week.blocks")}
        </div>
        {data.top_blocks.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.week.noBlocks")}</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {data.top_blocks.map((b, i) => (
              <div key={i} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: "8px 10px", borderRadius: 10, background: "var(--obsidian)", fontSize: 13 }}>
                <span style={{ fontWeight: 700, color: "var(--volt)" }}>
                  {t(`dash.demand.dow.${DOW_KEYS[b.dow]}`)} {b.start_hour}:00–{b.end_hour}:00
                </span>
                <span>{b.expected_offers.toFixed(1)} {t("dash.demand.week.expected")}</span>
                {b.reasons.flights != null && b.reasons.flights > 1.2 && (
                  <span style={{ color: "var(--silver)" }}><Icon name="plane" size={12} color="currentColor" /> {t("dash.demand.week.flights")} ×{b.reasons.flights}</span>
                )}
                {(b.reasons.events ?? []).map((ev) => (
                  <span key={ev} style={{ color: "var(--silver)" }}><Icon name="calendar" size={12} color="currentColor" /> {ev}</span>
                ))}
                {b.reasons.holiday && <span style={{ color: "var(--silver)" }}>{t("dash.demand.week.holiday")}: {b.reasons.holiday}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ overflowX: "auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "34px repeat(24, minmax(11px, 1fr))", gap: 2, minWidth: 360 }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} style={{ fontSize: 9, color: "var(--silver)", textAlign: "center" }}>{h % 3 === 0 ? h : ""}</div>
          ))}
          {data.grid.map((row, d) => (
            <FragmentRow key={d} d={d} row={row} max={max} sel={sel} setSel={setSel} privateByCell={privateByCell} label={t(`dash.demand.dow.${DOW_KEYS[d]}`)} />
          ))}
        </div>
      </div>

      {cell && sel && (
        <div style={{ padding: 12, borderRadius: 12, border: "1px solid var(--line-strong)", background: "var(--obsidian)", fontSize: 13, display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontWeight: 700 }}>
            {t(`dash.demand.dow.${DOW_KEYS[sel.d]}`)} {sel.h}:00 — <span style={{ color: "var(--volt)" }}>{pct(cell.p15)}</span> {t("dash.demand.week.p15")}
          </div>
          <div style={{ color: "var(--silver)" }}>
            {cell.mean.toFixed(1)} ({cell.lo.toFixed(1)}–{cell.hi.toFixed(1)}) {t("dash.demand.week.expected")}
          </div>
          <div style={{ color: "var(--silver)" }}>
            {pct(cell.own_share)} {t("dash.demand.week.ownData")} · {((cell.reasons.own_minutes ?? 0) / 60).toFixed(1)} {t("dash.demand.week.hoursLogged")}
            {isThin(cell.own_share) ? ` · ${t("dash.demand.week.thin")}` : ""}
          </div>
          {(() => {
            const extras: string[] = [];
            if (cell.reasons.flights != null && cell.reasons.flights > 1.2) {
              extras.push(`${t("dash.demand.week.flights")} ×${cell.reasons.flights}`);
            }
            if ((cell.reasons.events ?? []).length) {
              extras.push(`${t("dash.demand.week.events")}: ${cell.reasons.events!.join(", ")}`);
            }
            if (cell.reasons.holiday) {
              extras.push(`${t("dash.demand.week.holiday")}: ${cell.reasons.holiday}`);
            }
            if (privateByCell.has(`${sel.d}-${sel.h}`)) {
              extras.push(t("dash.demand.week.privateRide"));
            }
            return extras.length ? <div style={{ color: "var(--silver)" }}>{extras.join(" · ")}</div> : null;
          })()}
        </div>
      )}

      {data.computed_at && (
        <div style={{ fontSize: 11, color: "var(--silver)" }}>
          {t("dash.demand.week.computed")} {new Date(data.computed_at).toLocaleString(undefined, { timeZone: "America/Denver" })}
        </div>
      )}
    </div>
  );
}

function FragmentRow({
  d, row, max, sel, setSel, privateByCell, label,
}: {
  d: number;
  row: WeekCell[];
  max: number;
  sel: { d: number; h: number } | null;
  setSel: (s: { d: number; h: number }) => void;
  privateByCell: Set<string>;
  label: string;
}) {
  return (
    <>
      <div style={{ fontSize: 11, color: "var(--silver)", display: "flex", alignItems: "center" }}>{label}</div>
      {row.map((c, h) => {
        const on = sel?.d === d && sel?.h === h;
        const thin = (c?.own_share ?? 0) < THIN;
        const priv = privateByCell.has(`${d}-${h}`);
        return (
          <button
            key={h}
            aria-label={`${label} ${h}:00`}
            onClick={() => setSel({ d, h })}
            style={{
              height: 22,
              padding: 0,
              borderRadius: 3,
              border: on ? "2px solid var(--arctic)" : priv ? "2px solid #ffd166" : "1px solid rgba(255,255,255,0.06)",
              background: thin
                ? `repeating-linear-gradient(45deg, ${shade(c?.mean ?? 0, max)} 0 3px, rgba(0,0,0,0.35) 3px 5px)`
                : shade(c?.mean ?? 0, max),
              cursor: "pointer",
            }}
          />
        );
      })}
    </>
  );
}
