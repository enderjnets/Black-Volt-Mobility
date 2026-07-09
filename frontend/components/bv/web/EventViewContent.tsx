"use client";

import { useEffect } from "react";

import { pixelTrack } from "@/lib/analytics";

// Fire a Meta "ViewContent" once when an event landing loads — the top-of-funnel signal for
// event-landing ad campaigns. Lets Meta build audiences of event viewers and optimize before
// InitiateCheckout volume ramps, and enables retargeting people who viewed but didn't book.
// The landing is a server component, so this must run on the client. Deduped per slug per tab
// so re-renders/back-nav don't double-count.
export default function EventViewContent({
  slug,
  title,
  value,
}: {
  slug: string;
  title: string;
  value: number;
}) {
  useEffect(() => {
    try {
      const KEY = "bv_event_vc_fired";
      const fired = (sessionStorage.getItem(KEY) || "").split(",").filter(Boolean);
      if (fired.includes(slug)) return;
      fired.push(slug);
      sessionStorage.setItem(KEY, fired.join(","));
    } catch {
      // sessionStorage blocked (private mode) → fall through and still fire once.
    }
    pixelTrack("ViewContent", {
      content_name: title,
      content_type: "product",
      content_ids: [slug],
      value,
      currency: "USD",
    });
  }, [slug, title, value]);

  return null;
}
