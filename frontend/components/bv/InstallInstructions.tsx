"use client";

import { useEffect } from "react";

import { useI18n } from "@/lib/i18n";
import { isIOS, isSafari } from "@/lib/push";

/**
 * A dismissable instruction sheet for browsers that cannot fire the native install
 * prompt — every Safari (iOS and macOS). Chrome/Edge fire `beforeinstallprompt` and
 * never reach this. Shows the correct manual steps: iOS Add-to-Home-Screen (via Share)
 * or macOS Safari Add-to-Dock (via Share). Any other prompt-less browser falls back to
 * the generic "use the browser menu" hint.
 */
export function InstallInstructions({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const ios = isIOS();
  const macSafari = !ios && isSafari();
  const guided = ios || macSafari;

  // Close on Escape for desktop keyboard users.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const steps = ios
    ? [t("install.ios.s1"), t("install.ios.s2"), t("install.ios.s3")]
    : macSafari
      ? [t("install.mac.s1"), t("install.mac.s2")]
      : [t("install.menuHint")];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("install.help.title")}
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        background: "rgba(0,0,0,0.6)",
        padding: 16,
        fontFamily: "var(--font-sans)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 420,
          background: "var(--void)",
          border: "1px solid var(--volt)",
          borderRadius: 16,
          padding: 20,
          boxShadow: "0 20px 60px rgba(0,0,0,0.55)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            marginBottom: 14,
          }}
        >
          <strong style={{ fontSize: 16, color: "var(--arctic)" }}>{t("install.help.title")}</strong>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("install.dismiss")}
            style={{
              flexShrink: 0,
              background: "none",
              border: "none",
              color: "var(--fg3)",
              fontSize: 22,
              lineHeight: 1,
              cursor: "pointer",
              padding: 2,
            }}
          >
            ×
          </button>
        </div>

        {guided && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 14,
              padding: "8px 10px",
              borderRadius: 10,
              background: "var(--obsidian)",
              color: "var(--arctic)",
              fontSize: 13,
            }}
          >
            <ShareGlyph />
            <span>{t("install.help.share")}</span>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, textAlign: "left" }}>
              {guided && (
                <span
                  aria-hidden
                  style={{
                    flexShrink: 0,
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    background: "var(--volt)",
                    color: "var(--void)",
                    fontSize: 12,
                    fontWeight: 700,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {i + 1}
                </span>
              )}
              <span style={{ color: "var(--arctic)", fontSize: 14, lineHeight: 1.5 }}>{s}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The iOS/macOS "Share" glyph — a tray with an upward arrow. */
function ShareGlyph() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--volt)"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={{ flexShrink: 0 }}
    >
      <path d="M12 15V3" />
      <path d="M8 7l4-4 4 4" />
      <path d="M5 12v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7" />
    </svg>
  );
}
