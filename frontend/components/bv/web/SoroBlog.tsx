"use client";

import { useEffect, useRef } from "react";

import { useI18n } from "@/lib/i18n";

// Public Soro embed identifier for blackvoltmobility.com. This is NOT a secret —
// it is designed to live in the site's public HTML — so it is safe to commit inline.
// (When we ship our own blog engine, this component is the only thing that gets swapped.)
const SORO_EMBED_SRC =
  "https://app.trysoro.com/api/embed/00d74b10-fc6b-4bc5-84bf-b760de5a3bba?theme=dark";

/**
 * Renders the Soro blog widget under a branded heading. Soro's script injects the
 * article list / post content into the `#soro-blog` container client-side.
 *
 * The script is (re)created on every mount and removed on unmount so the widget
 * re-initializes cleanly on SPA re-entry and survives React StrictMode's double
 * mount. If Soro's embed is disabled (403), the container simply stays empty —
 * the heading and the rest of the page render unaffected.
 */
export function SoroBlog({ showHeader = true }: { showHeader?: boolean }) {
  const { t } = useI18n();
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // Drop any stale Soro script (StrictMode remount / client navigation) and
    // start from an empty container so the embed re-initializes deterministically.
    document.querySelectorAll("script[data-soro]").forEach((s) => s.remove());
    const host = hostRef.current;
    if (host) host.innerHTML = "";

    // Soro's embed registers a window `popstate` listener that removing the
    // <script> tag does NOT undo — left in place it fires on back/forward on
    // OTHER pages after an SPA exit (overwriting document.title and throwing on
    // its detached container). Intercept addEventListener only while the embed
    // loads, capture that specific handler (identified by its own internals),
    // and detach it on unmount.
    const captured: EventListener[] = [];
    const originalAdd = window.addEventListener;
    (window as any).addEventListener = function (type: string, fn: any, opts?: any) {
      if (type === "popstate" && typeof fn === "function" && /getRequestedSlug|showArticle/.test(String(fn))) {
        captured.push(fn);
      }
      return originalAdd.call(window, type, fn, opts);
    };
    const restoreAdd = () => {
      window.addEventListener = originalAdd;
    };

    const script = document.createElement("script");
    script.src = SORO_EMBED_SRC;
    script.defer = true;
    script.setAttribute("data-soro", "1");
    script.onload = restoreAdd; // fires after the embed executed (and registered its listener)
    script.onerror = restoreAdd;
    document.body.appendChild(script);

    return () => {
      restoreAdd();
      captured.forEach((fn) => window.removeEventListener("popstate", fn));
      script.remove();
      // Sweep the <head> artifacts the embed leaves behind so they can't leak
      // onto other pages: its canonical (tagged data-soro) and its Blog JSON-LD
      // (untagged — identified by content; our own pages' JSON-LD lives in <body>).
      document.querySelectorAll('link[rel="canonical"][data-soro]').forEach((n) => n.remove());
      document.head.querySelectorAll('script[type="application/ld+json"]').forEach((n) => {
        if (/"@type"\s*:\s*"Blog(Posting)?"/.test(n.textContent || "")) n.remove();
      });
      if (host) host.innerHTML = "";
    };
  }, []);

  return (
    <>
      {showHeader && (
        <header style={{ marginBottom: 24 }}>
          <h1
            style={{
              fontSize: 30,
              fontWeight: 800,
              color: "var(--arctic)",
              margin: "0 0 8px",
              letterSpacing: "-0.02em",
            }}
          >
            {t("blog.title")}
          </h1>
          <p
            style={{ fontSize: 15, color: "var(--fg2)", margin: 0, lineHeight: 1.55, maxWidth: 620 }}
          >
            {t("blog.intro")}
          </p>
        </header>
      )}
      <div ref={hostRef} id="soro-blog" style={{ minHeight: 320 }} />
    </>
  );
}
