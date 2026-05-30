"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { GoogleG } from "../ui";
import { useI18n } from "@/lib/i18n";

export interface BvUser {
  name: string;
  email: string;
  since: string;
}

export const BV_USER: BvUser = {
  name: "Alex Rivera",
  email: "alex.rivera@gmail.com",
  since: "May 2025",
};

export function SignInModal({ onClose, onSignIn }: { onClose: () => void; onSignIn: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const go = () => {
    setBusy(true);
    setTimeout(() => onSignIn(), 800);
  };
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        background: "rgba(5,5,9,0.72)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 380,
          background: "var(--obsidian)",
          border: "1px solid var(--volt-border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-volt)",
          padding: 30,
          textAlign: "center",
          position: "relative",
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          style={{ position: "absolute", top: 14, right: 14, background: "none", border: "none", cursor: "pointer", padding: 4 }}
        >
          <Icon name="x" size={18} color="var(--silver)" />
        </button>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 18 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              background: "var(--obsidian-2)",
              border: "1px solid var(--volt-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-volt-sm)",
            }}
          >
            <Icon name="zap" size={26} color="var(--volt)" fill="var(--volt)" />
          </div>
        </div>
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 24,
            color: "var(--arctic)",
            margin: "0 0 8px",
          }}
        >
          {t("auth.welcome")}
        </h2>
        <p
          style={{
            fontSize: 14,
            lineHeight: 1.5,
            color: "var(--silver)",
            margin: "0 0 24px",
            fontFamily: "var(--font-sans)",
          }}
        >
          {t("auth.subtitle")}
        </p>

        <button
          onClick={go}
          disabled={busy}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 11,
            background: "var(--arctic)",
            color: "#1f2024",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "13px 18px",
            fontSize: 15,
            fontWeight: 600,
            fontFamily: "var(--font-sans)",
            cursor: busy ? "default" : "pointer",
            opacity: busy ? 0.7 : 1,
            transition: "opacity .15s",
          }}
        >
          {busy ? (
            t("auth.signingin")
          ) : (
            <>
              <GoogleG size={20} />
              {t("auth.google")}
            </>
          )}
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "18px 0" }}>
          <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
          <span style={{ fontSize: 11, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
            {t("auth.or")}
          </span>
          <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            borderRadius: "var(--radius-md)",
            padding: "12px 14px",
            marginBottom: 18,
          }}
        >
          <Icon name="phone" size={17} color="var(--silver)" />
          <span style={{ color: "var(--silver)", fontSize: 14 }}>{t("auth.phone")}</span>
        </div>

        <p style={{ fontSize: 11.5, color: "var(--fg3)", lineHeight: 1.5, margin: 0 }}>{t("auth.terms")}</p>
      </div>
    </div>
  );
}
