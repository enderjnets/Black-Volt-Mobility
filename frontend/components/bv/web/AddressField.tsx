"use client";

/* Passenger-portal address input with Google Places autocomplete. Mirrors the
   look of <Field> (ui.tsx) but wraps it in a relative container + the shared
   SuggestionDropdown. Drop-in replacement for <Field> on the booking form. */

import { useState } from "react";

import { Icon } from "../Icon";
import { SuggestionDropdown, useAddressSuggest } from "../AddressAutocomplete";

export function AddressField({
  icon,
  label,
  value,
  placeholder,
  onChange,
}: {
  icon?: string;
  label?: string;
  value: string;
  placeholder?: string;
  onChange: (v: string) => void;
}) {
  const [focus, setFocus] = useState(false);
  const ctl = useAddressSuggest({ onPick: onChange });

  return (
    <label style={{ display: "block" }}>
      {label && (
        <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7, fontFamily: "var(--font-sans)" }}>
          {label}
        </div>
      )}
      <div ref={ctl.containerRef} style={{ position: "relative" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: "var(--obsidian-3)",
            borderRadius: "var(--radius-md)",
            padding: "12px 14px",
            border: `1px solid ${focus ? "var(--volt)" : "var(--line-strong)"}`,
            boxShadow: focus ? "0 0 0 3px var(--volt-bg)" : "none",
            transition: "all .15s ease-out",
          }}
        >
          {icon && <Icon name={icon} size={18} color={focus ? "var(--volt)" : "var(--silver)"} />}
          <input
            type="text"
            value={value}
            placeholder={placeholder}
            autoComplete="off"
            onChange={(e) => {
              onChange(e.target.value);
              ctl.handleType(e.target.value);
            }}
            onKeyDown={ctl.handleKeyDown}
            onFocus={() => {
              setFocus(true);
              if (value.trim().length >= 3) ctl.handleType(value);
            }}
            onBlur={() => setFocus(false)}
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              color: "var(--arctic)",
              fontSize: 14,
              fontFamily: "var(--font-sans)",
            }}
          />
        </div>
        <SuggestionDropdown ctl={ctl} />
      </div>
    </label>
  );
}
