"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { Field, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { BV_CLIENTS, type Client } from "./data";

const TIER_TONE: Record<string, "volt" | "muted" | "success"> = {
  VIP: "volt",
  Regular: "muted",
  New: "success",
};

function ClientRow({ c }: { c: Client }) {
  const { t } = useI18n();
  const [h, setH] = useState(false);
  return (
    <div
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr 80px 110px 90px",
        gap: 14,
        alignItems: "center",
        padding: "13px 16px",
        borderRadius: "var(--radius-md)",
        background: h ? "var(--obsidian-2)" : "transparent",
        transition: "background .12s",
        minWidth: 620,
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
          }}
        >
          <Icon name="user" size={16} color="var(--silver)" />
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>{c.name}</div>
          <div style={{ fontSize: 11, color: "var(--fg3)" }}>{t("dash.prefers", { lang: c.lang })}</div>
        </div>
      </div>
      <div style={{ fontSize: 13, color: "var(--silver)" }}>{c.phone}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)" }}>{c.rides}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)" }}>${c.spend.toLocaleString()}</div>
      <Pill tone={TIER_TONE[c.tier]} icon={c.tier === "VIP" ? "star" : undefined}>
        {t(`dash.tier.${c.tier}`)}
      </Pill>
    </div>
  );
}

export function Clients() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  return (
    <div style={{ padding: 28 }}>
      <div style={{ marginBottom: 18, maxWidth: 320 }}>
        <Field icon="search" placeholder={t("dash.searchClients")} value={q} onChange={setQ} />
      </div>
      <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 6, overflowX: "auto" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr 80px 110px 90px",
            gap: 14,
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
          <span>{t("dash.col.phone")}</span>
          <span>{t("dash.col.rides")}</span>
          <span>{t("dash.col.lifetime")}</span>
          <span>{t("dash.col.tier")}</span>
        </div>
        {BV_CLIENTS.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())).map((c, i) => (
          <ClientRow key={i} c={c} />
        ))}
      </div>
    </div>
  );
}
