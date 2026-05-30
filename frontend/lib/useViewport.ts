"use client";

import { useEffect, useState } from "react";

/* Viewport hook. Breakpoints mirror the design system:
   phone < 640 · compact < 900 (bottom-nav layout) · desktop >= 900.
   SSR-safe: defaults to desktop, corrects on mount. */
export function useViewport() {
  const [w, setW] = useState(1200);
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setW(window.innerWidth));
    };
    window.addEventListener("resize", on);
    on();
    return () => {
      window.removeEventListener("resize", on);
      cancelAnimationFrame(raf);
    };
  }, []);
  return { w, phone: w < 640, compact: w < 900, desktop: w >= 900 };
}
