"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "./Icon";
import { useI18n } from "@/lib/i18n";
import {
  getPushConfig,
  isIOS,
  isStandalone,
  isSubscribed,
  pushSupported,
  subscribePush,
  unsubscribePush,
} from "@/lib/push";

type State = "loading" | "hidden" | "ios-install" | "denied" | "on" | "off";

/**
 * Push-notification opt-in control, shared by the driver dashboard and the
 * passenger site. Renders nothing until it knows push is available and enabled;
 * on iOS-not-installed it shows the "Add to Home Screen" hint instead (Safari can
 * only push from an installed PWA). Enabling always runs from this button's tap —
 * Safari requires a user gesture for the permission prompt.
 */
export function PushOptIn({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  const [state, setState] = useState<State>("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    if (!pushSupported()) return setState("hidden");
    let cfg;
    try {
      cfg = await getPushConfig();
    } catch {
      return setState("hidden");
    }
    if (!cfg.enabled) return setState("hidden");
    if (isIOS() && !isStandalone()) return setState("ios-install");
    const perm = Notification.permission;
    if (perm === "denied") return setState("denied");
    if (perm === "granted") return setState((await isSubscribed()) ? "on" : "off");
    return setState("off");
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const enable = useCallback(async () => {
    setBusy(true);
    setError(false);
    try {
      const ok = await subscribePush();
      if (ok) setState("on");
      else setState(Notification.permission === "denied" ? "denied" : "off");
      if (!ok) setError(true);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }, []);

  const disable = useCallback(async () => {
    setBusy(true);
    try {
      await unsubscribePush();
      setState("off");
    } finally {
      setBusy(false);
    }
  }, []);

  if (state === "loading" || state === "hidden") return null;

  const wrap: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: compact ? "10px 16px" : "14px 16px",
    borderTop: compact ? "1px solid var(--line)" : "none",
    background: compact ? "transparent" : "var(--volt-bg)",
    borderRadius: compact ? 0 : 12,
    fontFamily: "var(--font-sans)",
  };
  const label: React.CSSProperties = {
    flex: 1,
    minWidth: 0,
    fontSize: 13,
    color: "var(--arctic)",
    lineHeight: 1.4,
  };
  const btn: React.CSSProperties = {
    flexShrink: 0,
    padding: "7px 12px",
    borderRadius: 8,
    border: "1px solid var(--line)",
    background: "var(--volt)",
    color: "var(--void)",
    fontSize: 12,
    fontWeight: 700,
    cursor: busy ? "wait" : "pointer",
    fontFamily: "var(--font-sans)",
    opacity: busy ? 0.7 : 1,
  };

  if (state === "ios-install") {
    return (
      <div style={wrap}>
        <span style={{ flexShrink: 0 }}>
          <Icon name="bell" size={16} color="var(--volt)" />
        </span>
        <span style={label}>{t("push.iosInstall")}</span>
      </div>
    );
  }

  if (state === "denied") {
    return (
      <div style={wrap}>
        <span style={{ flexShrink: 0 }}>
          <Icon name="bell" size={16} color="var(--fg3)" />
        </span>
        <span style={{ ...label, color: "var(--fg3)" }}>{t("push.blocked")}</span>
      </div>
    );
  }

  const on = state === "on";
  return (
    <div style={wrap}>
      <span style={{ flexShrink: 0 }}>
        <Icon name="bell" size={16} color={on ? "var(--volt)" : "var(--fg3)"} />
      </span>
      <span style={label}>
        {on ? t("push.on") : error ? t("push.failed") : t("push.desc")}
      </span>
      <button
        type="button"
        onClick={on ? disable : enable}
        disabled={busy}
        style={on ? { ...btn, background: "transparent", color: "var(--fg3)" } : btn}
      >
        {busy ? t("push.busy") : on ? t("push.turnOff") : t("push.turnOn")}
      </button>
    </div>
  );
}
