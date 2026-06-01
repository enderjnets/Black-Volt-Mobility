"use client";

/* Global usage tracker. Mounted once in the root layout, so it covers BOTH the
   passenger portal and the driver dashboard. Emits session_start once, a
   pageview on every route change, and a page_duration for the page being left
   (also on tab hide / unload via sendBeacon). Renders nothing. */

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { flush, trackDuration, trackPageview, trackSessionStart } from "@/lib/analytics";

export function AnalyticsTracker() {
  const pathname = usePathname();
  const last = useRef<{ path: string; t: number } | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!started.current) {
      started.current = true;
      trackSessionStart();
    }
    const now = Date.now();
    if (last.current) trackDuration(last.current.path, now - last.current.t);
    last.current = { path: pathname, t: now };
    trackPageview(pathname);
  }, [pathname]);

  useEffect(() => {
    const close = () => {
      if (last.current) {
        trackDuration(last.current.path, Date.now() - last.current.t);
        last.current = { path: last.current.path, t: Date.now() };
      }
      flush(true);
    };
    const onVis = () => {
      if (document.visibilityState === "hidden") close();
    };
    window.addEventListener("pagehide", close);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("pagehide", close);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return null;
}
