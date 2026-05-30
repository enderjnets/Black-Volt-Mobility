"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";
import { BV_RIDES } from "./data";
import { RideRow } from "./Overview";
import { Calendar } from "./Calendar";

export function Rides() {
  const { t } = useI18n();
  const [filter, setFilter] = useState("all");
  const [mode, setMode] = useState<"list" | "calendar">("list");
  const rides = filter === "all" ? BV_RIDES : BV_RIDES.filter((r) => r.status === filter);

  return (
    <div style={{ padding: 28 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", visibility: mode === "list" ? "visible" : "hidden" }}>
          {(
            [
              ["all", t("dash.filter.all")],
              ["upcoming", t("dash.filter.upcoming")],
              ["active", t("dash.filter.active")],
              ["done", t("dash.filter.done")],
            ] as const
          ).map(([v, l]) => (
            <button
              key={v}
              onClick={() => setFilter(v)}
              style={{
                padding: "8px 16px",
                borderRadius: "var(--radius-full)",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                fontFamily: "var(--font-sans)",
                background: filter === v ? "var(--volt-bg-20)" : "var(--obsidian)",
                color: filter === v ? "var(--volt)" : "var(--silver)",
                border: `1px solid ${filter === v ? "var(--volt-border)" : "var(--line-strong)"}`,
              }}
            >
              {l}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 4, background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 3 }}>
          {(
            [
              ["list", t("dash.view.list"), "layout-dashboard"],
              ["calendar", t("dash.view.calendar"), "calendar"],
            ] as const
          ).map(([v, l, ic]) => (
            <button
              key={v}
              onClick={() => setMode(v as "list" | "calendar")}
              style={{
                padding: "6px 14px",
                borderRadius: "var(--radius-full)",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                border: "none",
                fontFamily: "var(--font-sans)",
                display: "flex",
                alignItems: "center",
                gap: 7,
                background: mode === v ? "var(--volt-bg-20)" : "transparent",
                color: mode === v ? "var(--volt)" : "var(--silver)",
              }}
            >
              <Icon name={ic} size={15} color="currentColor" />
              {l}
            </button>
          ))}
        </div>
      </div>
      {mode === "calendar" ? (
        <Calendar />
      ) : (
        <div
          className="bv-table-wrap"
          style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 6, overflowX: "auto" }}
        >
          <div
            className="bv-table-head"
            style={{
              display: "grid",
              gridTemplateColumns: "130px 1fr 100px 60px 104px",
              gap: 12,
              padding: "12px 16px",
              fontSize: 11,
              color: "var(--fg3)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              borderBottom: "1px solid var(--line)",
              minWidth: 620,
            }}
          >
            <span>{t("dash.col.client")}</span>
            <span>{t("dash.col.route")}</span>
            <span>{t("dash.col.flight")}</span>
            <span>{t("dash.col.fare")}</span>
            <span>{t("dash.col.status")}</span>
          </div>
          <div className="bv-table-min" style={{ minWidth: 620 }}>
            {rides.map((r) => (
              <RideRow key={r.id} r={r} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
