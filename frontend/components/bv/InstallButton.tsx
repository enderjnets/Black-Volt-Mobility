"use client";

import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { isStandalone } from "@/lib/push";
import { installState, onInstallChange, registerServiceWorker, triggerInstall } from "@/lib/pwaInstall";
import { InstallInstructions } from "./InstallInstructions";

/**
 * A permanent "Install app" affordance for the footer / menu. Unlike the transient
 * InstallHint banner, this is always available (until installed). It fires the
 * native prompt when the browser offers one, and otherwise reveals short manual
 * instructions (iOS Add-to-Home-Screen, or "use the browser menu"). Renders nothing
 * once the app is installed / running standalone.
 */
export function InstallButton({ style }: { style?: React.CSSProperties }) {
  const { t } = useI18n();
  const [canPrompt, setCanPrompt] = useState(false);
  const [standalone, setStandalone] = useState(false);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    registerServiceWorker();
    setStandalone(isStandalone());
    const sync = () => setCanPrompt(installState().canPrompt);
    sync();
    return onInstallChange(sync);
  }, []);

  const onClick = useCallback(async () => {
    if (canPrompt) {
      const outcome = await triggerInstall();
      if (outcome === "unavailable") setHelp(true);
      return;
    }
    setHelp((v) => !v);
  }, [canPrompt]);

  if (standalone) return null;

  const linkStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "none",
    border: "none",
    padding: 0,
    cursor: "pointer",
    color: "inherit",
    font: "inherit",
    fontFamily: "var(--font-sans)",
    ...style,
  };

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
      <button type="button" onClick={onClick} style={linkStyle}>
        <span aria-hidden style={{ fontSize: "1em" }}>⬇</span>
        {t("install.button")}
      </button>
      {help && <InstallInstructions onClose={() => setHelp(false)} />}
    </span>
  );
}
