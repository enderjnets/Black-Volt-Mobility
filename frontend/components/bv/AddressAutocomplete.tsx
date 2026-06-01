"use client";

/* Reusable address autocomplete: a headless hook + a brand-styled floating
   dropdown. Backed by placesAutocomplete() (Google Places via the backend).
   Used by both the passenger portal (AddressField) and the driver dashboard
   (AddRide pickup/dropoff). No i18n text inside — it shows a spinner while
   loading and simply hides when there are no results — so it drops into either
   surface (web useI18n vs AddRide's local BV_T) without coupling. */

import { type RefObject, useEffect, useRef, useState } from "react";

import { Icon } from "./Icon";
import { placesAutocomplete } from "@/lib/booking";

export interface Suggestion {
  description: string;
  place_id: string | null;
}

export interface SuggestCtl {
  suggestions: Suggestion[];
  open: boolean;
  loading: boolean;
  activeIndex: number;
  containerRef: RefObject<HTMLDivElement>;
  handleType: (text: string) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  pick: (description: string) => void;
  close: () => void;
}

const MIN_CHARS = 3;
const DEBOUNCE_MS = 350;

export function useAddressSuggest({ onPick }: { onPick: (description: string) => void }): SuggestCtl {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reqId = useRef(0);

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const close = () => {
    clearTimer();
    setOpen(false);
    setActiveIndex(-1);
  };

  const handleType = (text: string) => {
    clearTimer();
    const q = text.trim();
    if (q.length < MIN_CHARS) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }
    setOpen(true);
    setLoading(true);
    setActiveIndex(-1);
    const id = ++reqId.current;
    timer.current = setTimeout(async () => {
      try {
        const out = await placesAutocomplete(q);
        if (id !== reqId.current) return; // stale response — a newer keystroke won
        setSuggestions(out);
      } catch {
        if (id === reqId.current) setSuggestions([]);
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, DEBOUNCE_MS);
  };

  const pick = (description: string) => {
    clearTimer();
    reqId.current++; // invalidate any in-flight request
    onPick(description);
    setSuggestions([]);
    setOpen(false);
    setActiveIndex(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter") {
      if (activeIndex >= 0 && activeIndex < suggestions.length) {
        e.preventDefault();
        pick(suggestions[activeIndex].description);
      }
    } else if (e.key === "Escape") {
      close();
    }
  };

  // Close when clicking outside the field+dropdown wrapper. Inlined (stable
  // setters + refs only) so the listener binds once, not every render.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        if (timer.current) clearTimeout(timer.current);
        timer.current = null;
        setOpen(false);
        setActiveIndex(-1);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return { suggestions, open, loading, activeIndex, containerRef, handleType, handleKeyDown, pick, close };
}

/* Floating list rendered as a sibling of the input inside a position:relative
   wrapper. Mouse-down (not click) + preventDefault so selecting an item doesn't
   blur the input away before the pick lands. */
export function SuggestionDropdown({ ctl }: { ctl: SuggestCtl }) {
  if (!ctl.open) return null;
  const showSpinner = ctl.loading && ctl.suggestions.length === 0;
  if (!showSpinner && ctl.suggestions.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 6px)",
        left: 0,
        right: 0,
        zIndex: 40,
        background: "var(--obsidian)",
        border: "1px solid var(--volt-border)",
        borderRadius: "var(--radius-md)",
        boxShadow: "var(--shadow-volt)",
        overflow: "hidden",
        maxHeight: 260,
        overflowY: "auto",
      }}
    >
      {showSpinner ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px" }}>
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: "50%",
              border: "2px solid var(--volt-border)",
              borderTopColor: "var(--volt)",
              animation: "bv-spin 0.8s linear infinite",
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 13, color: "var(--silver)", fontFamily: "var(--font-sans)" }}>…</span>
        </div>
      ) : (
        ctl.suggestions.map((s, i) => (
          <button
            key={(s.place_id || s.description) + i}
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              ctl.pick(s.description);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              width: "100%",
              textAlign: "left",
              background: i === ctl.activeIndex ? "var(--volt-bg)" : "transparent",
              border: "none",
              borderBottom: i < ctl.suggestions.length - 1 ? "1px solid var(--line)" : "none",
              padding: "11px 14px",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
            }}
          >
            <Icon name="map-pin" size={16} color="var(--volt)" />
            <span style={{ fontSize: 13.5, color: "var(--arctic)", lineHeight: 1.4 }}>{s.description}</span>
          </button>
        ))
      )}
    </div>
  );
}
