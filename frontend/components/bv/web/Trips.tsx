"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { Card } from "../ui";
import { useI18n } from "@/lib/i18n";
import { useWeb } from "./WebShell";
import { MapPlaceholder } from "./Booking";

function ActionBtn({ icon, label, onClick }: { icon: string; label: string; onClick?: () => void }) {
  const [h, setH] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 5,
        padding: "12px 0",
        borderRadius: "var(--radius-md)",
        cursor: "pointer",
        fontFamily: "var(--font-sans)",
        fontSize: 12,
        fontWeight: 600,
        background: h ? "var(--obsidian-2)" : "var(--obsidian-3)",
        color: h ? "var(--arctic)" : "var(--silver)",
        border: "1px solid var(--line-strong)",
        transition: "all .14s",
      }}
    >
      <Icon name={icon} size={18} color="var(--volt)" />
      {label}
    </button>
  );
}

export function Trips() {
  const { t } = useI18n();
  const { openChat } = useWeb();
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");

  return (
    <div style={{ maxWidth: 520, margin: "0 auto", padding: "32px 0" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 28, color: "var(--arctic)", margin: 0 }}>
          {t("trips.title")}
        </h2>
        <div style={{ display: "flex", gap: 6 }}>
          {(
            [
              ["upcoming", t("trips.upcoming")],
              ["past", t("trips.past")],
            ] as const
          ).map(([v, l]) => (
            <button
              key={v}
              onClick={() => setTab(v)}
              style={{
                padding: "7px 14px",
                borderRadius: "var(--radius-full)",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                fontFamily: "var(--font-sans)",
                background: tab === v ? "var(--volt-bg-20)" : "transparent",
                color: tab === v ? "var(--volt)" : "var(--silver)",
                border: `1px solid ${tab === v ? "var(--volt-border)" : "var(--line-strong)"}`,
              }}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {tab === "upcoming" ? (
        <Card glow pad={0} style={{ overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 18px 12px" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                fontFamily: "var(--font-sans)",
                fontSize: 13,
                fontWeight: 600,
                color: "var(--volt)",
              }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: "50%",
                  background: "var(--volt)",
                  boxShadow: "var(--shadow-volt-sm)",
                }}
              />
              {t("trips.enroute")}
            </span>
            <span style={{ fontSize: 13, color: "var(--silver)" }}>
              {t("trips.arriving")}{" "}
              <b style={{ fontFamily: "var(--font-display)", color: "var(--arctic)", fontSize: 15 }}>6 min</b>
            </span>
          </div>

          <div style={{ padding: "0 18px" }}>
            <MapPlaceholder height={180} />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 18px" }}>
            <div
              style={{
                width: 46,
                height: 46,
                borderRadius: "50%",
                border: "2px solid var(--volt)",
                background: "var(--obsidian-3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Icon name="user" size={22} color="var(--silver)" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 17, color: "var(--arctic)" }}>
                Ender
              </div>
              <div style={{ fontSize: 12, color: "var(--silver)", display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="star" size={12} color="var(--volt)" fill="var(--volt)" /> 4.98 · Black Kia EV9 · ENV-4827
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, padding: "0 18px 16px" }}>
            <ActionBtn icon="message-circle" label={t("trips.message")} onClick={openChat} />
            <ActionBtn icon="phone" label={t("trips.call")} />
          </div>

          <div
            style={{
              margin: "0 18px 18px",
              padding: 14,
              borderRadius: "var(--radius-md)",
              background: "var(--obsidian-2)",
              border: "1px solid var(--line-strong)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600, color: "var(--arctic)" }}>
                <Icon name="plane" size={16} color="var(--volt)" /> {t("trips.flight")} UA 2293
              </span>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--success)",
                  background: "rgba(43,212,160,0.12)",
                  border: "1px solid rgba(43,212,160,0.4)",
                  borderRadius: "var(--radius-full)",
                  padding: "3px 10px",
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} /> {t("trips.ontime")}
              </span>
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              {(
                [
                  ["trips.gate", "B34"],
                  ["trips.lands", "14:05"],
                  ["trips.tracking", "Live"],
                ] as const
              ).map(([k, v], i) => (
                <div key={i} style={{ flex: 1 }}>
                  <div style={{ fontSize: 10, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 3 }}>
                    {t(k)}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-display)",
                      fontWeight: 700,
                      fontSize: 16,
                      color: i === 2 ? "var(--volt)" : "var(--arctic)",
                    }}
                  >
                    {v}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            { to: "Denver Intl (DEN)", from: "Downtown Denver", date: "May 24", fare: 74 },
            { to: "The Ritz-Carlton", from: "DEN", date: "May 18", fare: 82 },
            { to: "Boulder", from: "DEN", date: "May 11", fare: 110 },
          ].map((r, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                padding: "14px 16px",
                background: "var(--obsidian)",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--radius-lg)",
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Icon name="navigation" size={18} color="var(--volt)" />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>
                  {r.from} → {r.to}
                </div>
                <div style={{ fontSize: 12, color: "var(--fg3)" }}>{r.date}</div>
              </div>
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--arctic)" }}>
                ${r.fare}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
