"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "./Icon";
import { useI18n } from "@/lib/i18n";
import { isIOS, isStandalone } from "@/lib/push";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_KEY = "bv-install-hint-dismissed";

/**
 * A slim, dismissible "install this app" prompt. On Android/desktop it uses the
 * native `beforeinstallprompt`; on iOS Safari (which has no such event) it shows
 * the "Share → Add to Home Screen" instruction. Renders nothing once installed
 * (standalone) or after the user dismisses it (persisted in localStorage). Sits
 * above the mobile tab bar so it never covers navigation.
 */
export function InstallHint() {
  const { t } = useI18n();
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIOS, setShowIOS] = useState(false);
  const [dismissed, setDismissed] = useState(true); // hidden until we decide to show

  useEffect(() => {
    if (isStandalone()) return;
    if (typeof localStorage !== "undefined" && localStorage.getItem(DISMISS_KEY) === "1") return;
    setDismissed(false);

    const onPrompt = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);

    // iOS never fires beforeinstallprompt — offer manual A2HS instructions instead.
    if (isIOS() && !isStandalone()) setShowIOS(true);

    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  const install = useCallback(async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice.catch(() => undefined);
    setDeferred(null);
    dismiss();
  }, [deferred, dismiss]);

  if (dismissed) return null;
  const canInstall = deferred != null;
  if (!canInstall && !showIOS) return null;

  return (
    <div
      role="dialog"
      aria-label={t("install.title")}
      style={{
        position: "fixed",
        left: 12,
        right: 12,
        bottom: "calc(env(safe-area-inset-bottom, 0px) + 76px)",
        maxWidth: 520,
        margin: "0 auto",
        zIndex: 60,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "12px 14px",
        borderRadius: 14,
        background: "var(--void)",
        border: "1px solid var(--volt)",
        boxShadow: "0 10px 30px rgba(0,0,0,0.45)",
        fontFamily: "var(--font-sans)",
      }}
    >
      <span style={{ flexShrink: 0 }}>
        <Icon name="bell" size={18} color="var(--volt)" />
      </span>
      <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: "var(--arctic)", lineHeight: 1.4 }}>
        {canInstall ? t("install.desc") : t("install.iosDesc")}
      </span>
      {canInstall && (
        <button
          type="button"
          onClick={install}
          style={{
            flexShrink: 0,
            padding: "7px 12px",
            borderRadius: 8,
            border: "none",
            background: "var(--volt)",
            color: "var(--void)",
            fontSize: 12,
            fontWeight: 700,
            cursor: "pointer",
            fontFamily: "var(--font-sans)",
          }}
        >
          {t("install.cta")}
        </button>
      )}
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("install.dismiss")}
        style={{
          flexShrink: 0,
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--fg3)",
          fontSize: 18,
          lineHeight: 1,
          padding: 2,
        }}
      >
        ×
      </button>
    </div>
  );
}
