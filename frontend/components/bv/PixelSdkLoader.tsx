"use client";

import { useEffect } from "react";

/**
 * Loads the ~242KB Meta Pixel SDK (fbevents.js) OUT of the page-load window: on the
 * first real user interaction, or after a fallback timeout — whichever comes first.
 *
 * The fbq stub in MetaPixel already queues PageView + funnel events synchronously,
 * so nothing is lost; this only defers the heavy network+parse so it never competes
 * with the LCP hero/font for bandwidth on a throttled connection. When the SDK
 * loads it drains the queued calls.
 */
const SDK_SRC = "https://connect.facebook.net/en_US/fbevents.js";
const INTERACTIONS = ["pointerdown", "keydown", "touchstart", "scroll", "mousemove"] as const;
const FALLBACK_MS = 6000;

export function PixelSdkLoader() {
  useEffect(() => {
    if (document.getElementById("meta-pixel-sdk")) return;
    let done = false;

    const load = () => {
      if (done) return;
      done = true;
      cleanup();
      const s = document.createElement("script");
      s.id = "meta-pixel-sdk";
      s.src = SDK_SRC;
      s.async = true;
      document.head.appendChild(s);
    };

    const cleanup = () => {
      clearTimeout(timer);
      INTERACTIONS.forEach((e) => window.removeEventListener(e, load));
    };

    INTERACTIONS.forEach((e) => window.addEventListener(e, load, { once: true, passive: true }));
    const timer = setTimeout(load, FALLBACK_MS);
    return cleanup;
  }, []);

  return null;
}
