"use client";

/* Zero-dependency interactive SVG charts for the Insights dashboard.
   TrendChart: visitors + pageviews over time with a hover crosshair + tooltip.
   Donut: a category breakdown (e.g. devices) with hover highlight + center readout. */

import { useState } from "react";

type TrendPoint = { day: string; pageviews: number; visitors: number };

const W = 620;
const H = 180;
const PAD = { t: 16, r: 14, b: 24, l: 30 };

function niceDay(day: string): string {
  // day is "YYYY-MM-DD"; show "Jun 28"
  const parts = day.split("-");
  if (parts.length !== 3) return day;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const m = months[Math.max(0, Math.min(11, Number(parts[1]) - 1))];
  return `${m} ${Number(parts[2])}`;
}

export function TrendChart({
  data,
  labels,
}: {
  data: TrendPoint[];
  labels: { visitors: string; pageviews: string };
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return null;

  const n = data.length;
  const max = Math.max(1, ...data.map((d) => Math.max(d.pageviews, d.visitors)));
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => PAD.t + innerH - (v / max) * innerH;

  const line = (key: "pageviews" | "visitors") =>
    data.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(" ");
  const area = (key: "pageviews" | "visitors") =>
    `${line(key)} L${x(n - 1).toFixed(1)},${(PAD.t + innerH).toFixed(1)} L${x(0).toFixed(1)},${(PAD.t + innerH).toFixed(1)} Z`;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1)))));
  };

  const gridY = [0.25, 0.5, 0.75, 1].map((g) => PAD.t + innerH - g * innerH);
  const hv = hover != null ? data[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      {/* legend */}
      <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: 12, color: "var(--silver)" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--volt)" }} />
          {labels.visitors}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--silver)" }} />
          {labels.pageviews}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ display: "block", overflow: "visible" }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="bvVisitorsFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--volt)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--volt)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {gridY.map((gy, i) => (
          <line key={i} x1={PAD.l} y1={gy} x2={W - PAD.r} y2={gy} stroke="var(--line)" strokeWidth={1} />
        ))}
        <text x={PAD.l} y={PAD.t - 4} fontSize={10} fill="var(--fg3)">
          {max}
        </text>

        {/* pageviews (secondary, silver line) */}
        <path d={line("pageviews")} fill="none" stroke="var(--silver)" strokeWidth={1.5} strokeOpacity={0.7} />
        {/* visitors (primary, volt area + line) */}
        <path d={area("visitors")} fill="url(#bvVisitorsFill)" stroke="none" />
        <path d={line("visitors")} fill="none" stroke="var(--volt)" strokeWidth={2.2} />

        {/* x labels: first + last */}
        <text x={PAD.l} y={H - 6} fontSize={10} fill="var(--fg3)">
          {niceDay(data[0].day)}
        </text>
        <text x={W - PAD.r} y={H - 6} fontSize={10} fill="var(--fg3)" textAnchor="end">
          {niceDay(data[n - 1].day)}
        </text>

        {/* hover crosshair + dots */}
        {hv && (
          <>
            <line x1={x(hover!)} y1={PAD.t} x2={x(hover!)} y2={PAD.t + innerH} stroke="var(--volt)" strokeWidth={1} strokeDasharray="3 3" strokeOpacity={0.6} />
            <circle cx={x(hover!)} cy={y(hv.pageviews)} r={3.5} fill="var(--silver)" />
            <circle cx={x(hover!)} cy={y(hv.visitors)} r={4} fill="var(--volt)" stroke="var(--obsidian)" strokeWidth={1.5} />
          </>
        )}
      </svg>

      {/* tooltip */}
      {hv && (
        <div
          style={{
            position: "absolute",
            top: 26,
            left: `${(x(hover!) / W) * 100}%`,
            transform: `translateX(${hover! > n / 2 ? "-105%" : "5%"})`,
            background: "var(--obsidian-2)",
            border: "1px solid var(--line-strong)",
            borderRadius: 8,
            padding: "8px 10px",
            pointerEvents: "none",
            boxShadow: "var(--shadow-pop)",
            whiteSpace: "nowrap",
            zIndex: 5,
          }}
        >
          <div style={{ fontSize: 11, color: "var(--fg3)", marginBottom: 4 }}>{niceDay(hv.day)}</div>
          <div style={{ fontSize: 12.5, color: "var(--volt)", fontWeight: 600 }}>
            {hv.visitors} {labels.visitors.toLowerCase()}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--silver)" }}>
            {hv.pageviews} {labels.pageviews.toLowerCase()}
          </div>
        </div>
      )}
    </div>
  );
}

export type FunnelStep = { key: string; label: string; count: number };

export function FunnelChart({ steps, ofLabel, dropLabel }: { steps: FunnelStep[]; ofLabel: string; dropLabel: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const start = steps[0]?.count || 0;
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {steps.map((s, i) => {
        const pctStart = start > 0 ? Math.round((s.count / start) * 100) : 0;
        const prev = i > 0 ? steps[i - 1].count : s.count;
        const pctPrev = prev > 0 ? Math.round((s.count / prev) * 100) : 0;
        const drop = i > 0 ? prev - s.count : 0;
        const width = Math.max(6, pctStart); // % bar width, min visible
        const on = hover === i;
        return (
          <div
            key={s.key}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            style={{ position: "relative" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
              <span style={{ color: "var(--silver)" }}>{s.label}</span>
              <span style={{ color: "var(--arctic)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                {s.count}
                <span style={{ color: "var(--fg3)", fontWeight: 400, marginLeft: 8 }}>{pctStart}%</span>
              </span>
            </div>
            <div style={{ height: 26, background: "var(--obsidian-3)", borderRadius: 6, overflow: "hidden" }}>
              <div
                style={{
                  width: `${width}%`,
                  height: "100%",
                  background: on
                    ? "var(--volt)"
                    : "linear-gradient(90deg, var(--volt) 0%, rgba(0,229,255,0.55) 100%)",
                  borderRadius: 6,
                  transition: "filter .12s",
                  filter: on ? "brightness(1.1)" : "none",
                }}
              />
            </div>
            {on && i > 0 && (
              <div
                style={{
                  position: "absolute",
                  right: 0,
                  top: -2,
                  transform: "translateY(-100%)",
                  background: "var(--obsidian-2)",
                  border: "1px solid var(--line-strong)",
                  borderRadius: 8,
                  padding: "6px 9px",
                  fontSize: 12,
                  whiteSpace: "nowrap",
                  boxShadow: "var(--shadow-pop)",
                  zIndex: 5,
                }}
              >
                <span style={{ color: "var(--volt)" }}>{pctPrev}%</span>{" "}
                <span style={{ color: "var(--fg3)" }}>{ofLabel}</span>
                {drop > 0 && (
                  <span style={{ color: "var(--fg3)" }}>
                    {" "}· {drop} {dropLabel}
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const DONUT_COLORS = ["var(--volt)", "#7c5cff", "#34d399", "#f59e0b", "#f472b6", "#60a5fa"];

function arc(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const p = (a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x0, y0] = p(a0);
  const [x1, y1] = p(a1);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r},${r} 0 ${large} 1 ${x1.toFixed(2)},${y1.toFixed(2)}`;
}

export function Donut({ data }: { data: { label: string; count: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const rows = data.filter((d) => d.count > 0);
  if (!rows.length) return null;
  const total = rows.reduce((s, r) => s + r.count, 0);
  const size = 150;
  const cx = size / 2;
  const cy = size / 2;
  const r = 58;

  let acc = -Math.PI / 2; // start at top
  const segs = rows.map((row, i) => {
    const frac = row.count / total;
    const a0 = acc;
    const a1 = acc + frac * Math.PI * 2 - (rows.length > 1 ? 0.04 : 0);
    acc += frac * Math.PI * 2;
    return { ...row, i, a0, a1, frac };
  });

  const active = hover != null ? segs[hover] : null;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={150} height={150} style={{ flexShrink: 0 }}>
        {segs.map((s) => (
          <path
            key={s.label}
            d={arc(cx, cy, r, s.a0, s.a1)}
            fill="none"
            stroke={DONUT_COLORS[s.i % DONUT_COLORS.length]}
            strokeWidth={hover === s.i ? 22 : 16}
            strokeLinecap="butt"
            style={{ transition: "stroke-width .12s", cursor: "default" }}
            onMouseEnter={() => setHover(s.i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize={22} fontWeight={700} fill="var(--arctic)">
          {active ? `${Math.round(active.frac * 100)}%` : total}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize={11} fill="var(--fg3)">
          {active ? active.label : "total"}
        </text>
      </svg>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 120 }}>
        {segs.map((s) => (
          <div
            key={s.label}
            onMouseEnter={() => setHover(s.i)}
            onMouseLeave={() => setHover(null)}
            style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, opacity: hover == null || hover === s.i ? 1 : 0.5 }}
          >
            <span style={{ width: 10, height: 10, borderRadius: 3, background: DONUT_COLORS[s.i % DONUT_COLORS.length], flexShrink: 0 }} />
            <span style={{ color: "var(--silver)", flex: 1, textTransform: "capitalize" }}>{s.label}</span>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--arctic)", fontVariantNumeric: "tabular-nums" }}>
              {s.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
