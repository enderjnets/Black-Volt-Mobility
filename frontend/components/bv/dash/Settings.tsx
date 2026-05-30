"use client";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";

export function Settings() {
  const { t } = useI18n();
  return (
    <div style={{ padding: 28 }}>
      <div style={{ background: "var(--obsidian)", border: "1px dashed var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 56, textAlign: "center" }}>
        <div
          style={{
            display: "inline-flex",
            marginBottom: 16,
            width: 52,
            height: 52,
            borderRadius: 12,
            background: "var(--volt-bg)",
            border: "1px solid var(--volt-border)",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon name="settings" size={24} color="var(--volt)" />
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--arctic)", marginBottom: 8 }}>
          {t("dash.settings.title")}
        </div>
        <p style={{ fontSize: 14, color: "var(--silver)", maxWidth: 360, margin: "0 auto" }}>{t("dash.settings.body")}</p>
      </div>
    </div>
  );
}
