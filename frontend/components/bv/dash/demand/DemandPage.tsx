"use client";

/* "Where to wait" — three tabs: one-tap shift log (default while driving), the
   7×24 week planner, and the Uber export import. The tab lives in the URL
   (?tab=) so a phone reload lands where the driver was. */

import { useRouter, useSearchParams } from "next/navigation";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import { ImportTab } from "./ImportTab";
import { LogTab } from "./LogTab";
import { WeekTab } from "./WeekTab";

type Tab = "log" | "week" | "import";
const TABS: { id: Tab; icon: string; key: string }[] = [
  { id: "log", icon: "zap", key: "dash.demand.tab.log" },
  { id: "week", icon: "calendar", key: "dash.demand.tab.week" },
  { id: "import", icon: "upload", key: "dash.demand.tab.import" },
];

export function DemandPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = raw === "week" || raw === "import" ? raw : "log";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 900 }}>
      <div style={{ display: "flex", gap: 6 }} role="tablist">
        {TABS.map((tb) => {
          const active = tb.id === tab;
          return (
            <button
              key={tb.id}
              role="tab"
              aria-selected={active}
              onClick={() => router.replace(`/dashboard/demand?tab=${tb.id}`)}
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                minHeight: 44,
                borderRadius: 10,
                border: `1px solid ${active ? "var(--volt)" : "var(--line-strong)"}`,
                background: active ? "rgba(0,229,255,0.08)" : "var(--obsidian)",
                color: active ? "var(--volt)" : "var(--silver)",
                fontFamily: "var(--font-sans)",
                fontWeight: active ? 700 : 500,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              <Icon name={tb.icon} size={18} color="currentColor" />
              {t(tb.key)}
            </button>
          );
        })}
      </div>
      {tab === "log" && <LogTab />}
      {tab === "week" && <WeekTab />}
      {tab === "import" && <ImportTab />}
    </div>
  );
}
