"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { CHANGELOG, CURRENT_VERSION } from "@/lib/version";
import { useI18n } from "@/lib/i18n";

export function VersionButton() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="rounded-full border border-volt/30 px-2 py-0.5 text-[11px] font-medium text-volt hover:bg-volt/10"
      >
        v{CURRENT_VERSION}
      </button>
      {mounted && open &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
            onClick={() => setOpen(false)}
          >
            <div
              className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-xl border border-obsidian bg-obsidian p-6 shadow-volt"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-display text-lg font-semibold text-arctic">
                  {t("version.history")}
                </h2>
                <button
                  onClick={() => setOpen(false)}
                  className="text-sm text-silver hover:text-arctic"
                >
                  {t("version.close")}
                </button>
              </div>
              <div className="space-y-5">
                {CHANGELOG.map((e) => (
                  <div key={e.version}>
                    <div className="flex items-baseline gap-2">
                      <span className="font-display font-semibold text-volt">v{e.version}</span>
                      <span className="text-xs text-silver">{e.date}</span>
                    </div>
                    <p className="text-sm font-medium text-arctic">{e.title}</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-silver">
                      {e.changes.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
