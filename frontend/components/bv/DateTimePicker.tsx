"use client";

/* Black Volt Mobility — branded date & time pickers.
   Fully clickable (no typing required), identical on phone and desktop, in the
   Black Volt aesthetic. Drop-in for the old native date/time inputs: same value
   formats (date = "YYYY-MM-DD", time = "HH:MM" 24h) so callers and the shared
   scheduling helpers in lib/datetime keep working. */

import { type CSSProperties, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "./Icon";
import { pad2, formatDateDisplay, formatTimeDisplay } from "@/lib/datetime";

type Lang = string;

const DICT: Record<string, Record<string, string>> = {
  en: {
    today: "Today", tomorrow: "Tomorrow", in2: "+2 days",
    datePh: "Select date", timePh: "Select time", done: "Done", clear: "Clear",
    am: "AM", pm: "PM", hour: "Hour", minute: "Min",
  },
  es: {
    today: "Hoy", tomorrow: "Mañana", in2: "+2 días",
    datePh: "Elige fecha", timePh: "Elige hora", done: "Listo", clear: "Borrar",
    am: "AM", pm: "PM", hour: "Hora", minute: "Min",
  },
};
const tr = (lang: Lang, k: string) => (DICT[lang] || DICT.en)[k] || DICT.en[k];

// Local YYYY-MM-DD for a Date (avoids UTC drift from toISOString).
const ymd = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

function todayLocal(): Date {
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}

// Shared open/close state with outside-click + Escape (mirrors AddressAutocomplete).
function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

// Field chrome shared with RideField: label row + bordered trigger + popover.
function FieldShell({
  label, icon, display, placeholder, state, required, align = "left", open, setOpen, children,
}: {
  label: string;
  icon: string;
  display: string;
  placeholder: string;
  state: string;
  required?: boolean;
  align?: "left" | "right";
  open: boolean;
  setOpen: (v: boolean) => void;
  children: ReactNode;
}) {
  const border = state === "missing" ? "rgba(255,194,75,0.7)" : state === "ai" ? "var(--volt-border)" : "var(--line-strong)";
  const activeBorder = state === "missing" ? "var(--warning)" : "var(--volt)";
  const ring = state === "missing" ? "rgba(255,194,75,0.18)" : "var(--volt-bg)";
  const iconColor = open ? activeBorder : state === "missing" ? "var(--warning)" : "var(--silver)";
  return (
    <div style={{ display: "block" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
        <span style={{ fontSize: 12, color: "var(--fg3)", fontFamily: "var(--font-sans)" }}>
          {label}
          {required && <span style={{ color: "var(--warning)", marginLeft: 4 }}>*</span>}
        </span>
      </div>
      <div style={{ position: "relative" }}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            width: "100%",
            textAlign: "left",
            cursor: "pointer",
            background: "var(--obsidian-3)",
            borderRadius: "var(--radius-md)",
            padding: "11px 13px",
            border: `1px solid ${open ? activeBorder : border}`,
            boxShadow: open ? `0 0 0 3px ${ring}` : "none",
            transition: "all .15s ease-out",
            fontFamily: "var(--font-sans)",
          }}
        >
          <Icon name={icon} size={17} color={iconColor} />
          <span style={{ flex: 1, fontSize: 14, color: display ? "var(--arctic)" : "var(--fg3)" }}>
            {display || placeholder}
          </span>
          <Icon name="chevron-down" size={16} color="var(--silver)" />
        </button>
        {open && (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              ...(align === "right" ? { right: 0, left: "auto" } : { left: 0, right: "auto" }),
              zIndex: 40,
              width: 300,
              maxWidth: "calc(100vw - 24px)",
              background: "var(--obsidian)",
              border: "1px solid var(--volt-border)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-volt)",
              padding: 14,
            }}
          >
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

const chipStyle = (active: boolean): CSSProperties => ({
  padding: "8px 12px",
  minHeight: 40,
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontFamily: "var(--font-sans)",
  fontSize: 13,
  fontWeight: 600,
  background: active ? "var(--volt-bg-20)" : "var(--obsidian-3)",
  color: active ? "var(--volt)" : "var(--silver)",
  border: `1px solid ${active ? "var(--volt-border)" : "var(--line-strong)"}`,
  transition: "all .12s ease-out",
});

export function BVDatePicker({
  label, value, onChange, lang = "en", state = "normal", half, required, align = "left", icon = "calendar", placeholder, minToday = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  lang?: Lang;
  state?: string;
  half?: boolean;
  required?: boolean;
  align?: "left" | "right";
  icon?: string;
  placeholder?: string;
  minToday?: boolean;
}) {
  const { open, setOpen, ref } = usePopover();
  const today = todayLocal();
  const selected = /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "";
  // Calendar view month — follows the selected value, else today.
  const initial = selected ? new Date(Number(selected.slice(0, 4)), Number(selected.slice(5, 7)) - 1, 1) : today;
  const [view, setView] = useState({ y: initial.getFullYear(), m: initial.getMonth() });

  const weekdays = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(lang, { weekday: "short" });
    // 2024-01-01 is a Monday → Monday-first labels.
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
  }, [lang]);
  const monthLabel = useMemo(
    () => new Intl.DateTimeFormat(lang, { month: "long", year: "numeric" }).format(new Date(view.y, view.m, 1)),
    [lang, view],
  );

  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate();
  const lead = (new Date(view.y, view.m, 1).getDay() + 6) % 7; // Monday-based offset
  const todayStr = ymd(today);

  const pick = (d: string) => {
    onChange(d);
    setOpen(false);
  };
  const quick = (offset: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() + offset);
    pick(ymd(d));
  };
  const shift = (delta: number) => {
    const d = new Date(view.y, view.m + delta, 1);
    setView({ y: d.getFullYear(), m: d.getMonth() });
  };

  return (
    <div ref={ref} style={{ display: "block", gridColumn: half ? undefined : "1 / -1" }}>
      <FieldShell
        label={label}
        icon={icon}
        display={formatDateDisplay(selected, lang)}
        placeholder={placeholder || tr(lang, "datePh")}
        state={state}
        required={required}
        align={align}
        open={open}
        setOpen={setOpen}
      >
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button type="button" onClick={() => quick(0)} style={chipStyle(selected === todayStr)}>{tr(lang, "today")}</button>
          <button type="button" onClick={() => quick(1)} style={chipStyle(false)}>{tr(lang, "tomorrow")}</button>
          <button type="button" onClick={() => quick(2)} style={chipStyle(false)}>{tr(lang, "in2")}</button>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <button type="button" onClick={() => shift(-1)} style={navBtn}><Icon name="chevron-left" size={18} color="var(--silver)" /></button>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 14, color: "var(--arctic)", textTransform: "capitalize" }}>{monthLabel}</span>
          <button type="button" onClick={() => shift(1)} style={navBtn}><Icon name="chevron-right" size={18} color="var(--silver)" /></button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 4 }}>
          {weekdays.map((w, i) => (
            <div key={i} style={{ textAlign: "center", fontSize: 10, color: "var(--fg3)", fontFamily: "var(--font-sans)", textTransform: "uppercase", padding: "2px 0" }}>{w}</div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
          {Array.from({ length: lead }, (_, i) => <div key={`b${i}`} />)}
          {Array.from({ length: daysInMonth }, (_, i) => {
            const day = i + 1;
            const ds = `${view.y}-${pad2(view.m + 1)}-${pad2(day)}`;
            const isSel = ds === selected;
            const isToday = ds === todayStr;
            const disabled = minToday && ds < todayStr;
            return (
              <button
                key={day}
                type="button"
                disabled={disabled}
                onClick={() => pick(ds)}
                style={{
                  height: 38,
                  borderRadius: "var(--radius-sm)",
                  cursor: disabled ? "not-allowed" : "pointer",
                  fontFamily: "var(--font-sans)",
                  fontSize: 13,
                  fontVariantNumeric: "tabular-nums",
                  background: isSel ? "var(--volt)" : "transparent",
                  color: isSel ? "var(--void)" : disabled ? "var(--obsidian-3)" : "var(--silver)",
                  fontWeight: isSel || isToday ? 700 : 500,
                  border: isToday && !isSel ? "1px solid var(--volt-border)" : "1px solid transparent",
                  transition: "all .1s ease-out",
                }}
              >
                {day}
              </button>
            );
          })}
        </div>
      </FieldShell>
    </div>
  );
}

const navBtn: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: 36,
  height: 36,
  borderRadius: "var(--radius-md)",
  background: "var(--obsidian-3)",
  border: "1px solid var(--line-strong)",
  cursor: "pointer",
};

const QUICK_TIMES = ["06:00", "06:30", "07:00", "08:00", "09:00", "12:00", "15:00", "18:00"];

export function BVTimePicker({
  label, value, onChange, lang = "en", state = "normal", half, required, align = "right", icon = "clock", placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  lang?: Lang;
  state?: string;
  half?: boolean;
  required?: boolean;
  align?: "left" | "right";
  icon?: string;
  placeholder?: string;
}) {
  const { open, setOpen, ref } = usePopover();
  const m = value.match(/^(\d{1,2}):(\d{2})$/);
  const h24 = m ? Number(m[1]) : 9;
  const min = m ? Number(m[2]) : 0;
  const isPm = h24 >= 12;
  const h12 = ((h24 + 11) % 12) + 1;

  const emit = (nh12: number, nmin: number, pm: boolean) => {
    let h = nh12 % 12;
    if (pm) h += 12;
    onChange(`${pad2(h)}:${pad2(nmin)}`);
  };
  const stepHour = (d: number) => emit(((h12 - 1 + d + 12) % 12) + 1, min, isPm);
  const stepMin = (d: number) => {
    const total = (Math.round(min / 5) * 5 + d * 5 + 60) % 60;
    emit(h12, total, isPm);
  };
  const setMeridiem = (pm: boolean) => emit(h12, min, pm);

  return (
    <div ref={ref} style={{ display: "block", gridColumn: half ? undefined : "1 / -1" }}>
      <FieldShell
        label={label}
        icon={icon}
        display={formatTimeDisplay(value, lang)}
        placeholder={placeholder || tr(lang, "timePh")}
        state={state}
        required={required}
        align={align}
        open={open}
        setOpen={setOpen}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
          {QUICK_TIMES.map((qt) => (
            <button key={qt} type="button" onClick={() => onChange(qt)} style={chipStyle(value === qt)}>
              {formatTimeDisplay(qt, lang)}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
          <Stepper label={tr(lang, "hour")} display={String(h12)} onUp={() => stepHour(1)} onDown={() => stepHour(-1)} />
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--silver)" }}>:</span>
          <Stepper label={tr(lang, "minute")} display={pad2(min)} onUp={() => stepMin(1)} onDown={() => stepMin(-1)} />
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginLeft: 4 }}>
            <button type="button" onClick={() => setMeridiem(false)} style={chipStyle(!isPm)}>{tr(lang, "am")}</button>
            <button type="button" onClick={() => setMeridiem(true)} style={chipStyle(isPm)}>{tr(lang, "pm")}</button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          style={{
            marginTop: 14,
            width: "100%",
            minHeight: 42,
            borderRadius: "var(--radius-md)",
            background: "var(--volt-bg-20)",
            color: "var(--volt)",
            border: "1px solid var(--volt-border)",
            cursor: "pointer",
            fontFamily: "var(--font-sans)",
            fontSize: 14,
            fontWeight: 700,
          }}
        >
          {tr(lang, "done")}
        </button>
      </FieldShell>
    </div>
  );
}

function Stepper({ label, display, onUp, onDown }: { label: string; display: string; onUp: () => void; onDown: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <button type="button" onClick={onUp} style={navBtn}><Icon name="chevron-left" size={18} color="var(--silver)" style={{ transform: "rotate(90deg)" }} /></button>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)", fontVariantNumeric: "tabular-nums", minWidth: 36, textAlign: "center" }}>{display}</div>
      <button type="button" onClick={onDown} style={navBtn}><Icon name="chevron-left" size={18} color="var(--silver)" style={{ transform: "rotate(-90deg)" }} /></button>
      <span style={{ fontSize: 10, color: "var(--fg3)", fontFamily: "var(--font-sans)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
    </div>
  );
}
