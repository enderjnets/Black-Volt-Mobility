"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "./Icon";
import { InstallInstructions } from "./InstallInstructions";
import { useI18n } from "@/lib/i18n";
import { isNativeApp } from "@/lib/native";
import { isSafari, isStandalone } from "@/lib/push";
import { installState, onInstallChange, registerServiceWorker, triggerInstall } from "@/lib/pwaInstall";

const DISMISS_KEY = "bv-install-hint-dismissed";

/**
 * A slim, dismissible "install this app" prompt. Registers the service worker on
 * every load (what makes the app installable at all), then uses Chrome's captured
 * `beforeinstallprompt`; on iOS Safari (no such event) it shows the "Share → Add to
 * Home Screen" instruction. Renders nothing once installed (standalone) or after
 * the user dismisses it. Sits above the mobile tab bar.
 */
export function InstallHint() {
  const { t } = useI18n();
  const [canInstall, setCanInstall] = useState(false);
  const [showIOS, setShowIOS] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [dismissed, setDismissed] = useState(true); // hidden until we decide to show

  useEffect(() => {
    // No "add to home screen" prompt inside the native app.
    if (isNativeApp()) return;
    registerServiceWorker();
    if (isStandalone()) return;
    if (typeof localStorage !== "undefined" && localStorage.getItem(DISMISS_KEY) === "1") return;
    setDismissed(false);

    const sync = () => setCanInstall(installState().canPrompt);
    sync();
    const unsub = onInstallChange(sync);

    // Safari (iOS + macOS) never fires beforeinstallprompt — offer manual instructions instead.
    if (isSafari() && !isStandalone()) setShowIOS(true);

    return unsub;
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
    await triggerInstall();
    dismiss();
  }, [dismiss]);

  if (dismissed) return null;
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
        {t("install.desc")}
      </span>
      <button
        type="button"
        onClick={canInstall ? install : () => setShowHelp(true)}
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
      {showHelp && <InstallInstructions onClose={() => setShowHelp(false)} />}
    </div>
  );
}
