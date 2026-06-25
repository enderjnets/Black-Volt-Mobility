/* Standing ride-preference fields (conversation, temperature, music, luggage,
   pet, notes). Presentational + controlled: the parent owns the value and
   persists each change. Reused by the /account panel and the onboarding gate. */
"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";
import {
  RIDE_NOTES_MAX,
  RIDE_PREF_CHOICES,
  RIDE_PREF_TOGGLES,
  type RidePreferences,
} from "@/lib/profile";
import { Icon } from "../Icon";
import { Toggle } from "../ui";

function ChoicePills({
  value,
  options,
  busy,
  onPick,
}: {
  value: string;
  options: readonly { value: string; label: string }[];
  busy?: boolean;
  onPick: (v: string) => void;
}) {
  const { t } = useI18n();
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onPick(o.value)}
            disabled={busy}
            style={{
              padding: "6px 13px",
              borderRadius: "var(--radius-full)",
              cursor: busy ? "default" : "pointer",
              fontSize: 12.5,
              fontWeight: 600,
              fontFamily: "var(--font-sans)",
              background: on ? "var(--volt-bg-20)" : "var(--obsidian-3)",
              color: on ? "var(--volt)" : "var(--silver)",
              border: `1px solid ${on ? "var(--volt-border)" : "var(--line-strong)"}`,
            }}
          >
            {t(o.label)}
          </button>
        );
      })}
    </div>
  );
}

/** Read-only chip summary of a passenger's ride preferences (driver view).
 *  Returns null when everything is neutral so the driver sees nothing extra. */
export function RidePreferencesSummary({ value }: { value: RidePreferences }) {
  const { t } = useI18n();
  const chips: { icon: string; text: string }[] = [];
  for (const c of RIDE_PREF_CHOICES) {
    const v = value[c.field as keyof RidePreferences] as string;
    if (v && v !== "no_pref") {
      const opt = c.options.find((o) => o.value === v);
      if (opt) chips.push({ icon: c.icon, text: t(opt.label) });
    }
  }
  for (const tg of RIDE_PREF_TOGGLES) {
    if (value[tg.field as keyof RidePreferences]) chips.push({ icon: tg.icon, text: t(tg.label) });
  }
  const notes = (value.notes || "").trim();
  if (chips.length === 0 && !notes) return null;

  return (
    <div
      style={{
        background: "var(--obsidian-3)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-md)",
        padding: "12px 14px",
        marginBottom: 16,
      }}
    >
      <div
        style={{
          fontSize: 11,
          color: "var(--fg3)",
          fontFamily: "var(--font-sans)",
          textTransform: "uppercase",
          letterSpacing: 0.4,
          marginBottom: 9,
        }}
      >
        {t("dash.ride.prefs")}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
        {chips.map((ch, i) => (
          <span
            key={i}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: "var(--obsidian)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-full)",
              padding: "4px 11px",
              fontSize: 12.5,
              color: "var(--arctic)",
              fontFamily: "var(--font-sans)",
            }}
          >
            <Icon name={ch.icon} size={14} color="var(--volt)" />
            {ch.text}
          </span>
        ))}
      </div>
      {notes && (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 8,
            marginTop: 10,
            fontSize: 13,
            color: "var(--silver)",
            fontFamily: "var(--font-sans)",
          }}
        >
          <Icon name="pencil" size={14} color="var(--fg3)" />
          <span>{notes}</span>
        </div>
      )}
    </div>
  );
}

export function RidePreferencesFields({
  value,
  onChange,
  busy,
}: {
  value: RidePreferences;
  onChange: (patch: Partial<RidePreferences>) => void;
  busy?: boolean;
}) {
  const { t } = useI18n();
  const [notes, setNotes] = useState(value.notes ?? "");
  // Re-sync the textarea when the profile reloads from the server.
  useEffect(() => {
    setNotes(value.notes ?? "");
  }, [value.notes]);

  function commitNotes() {
    const trimmed = notes.trim();
    if (trimmed !== (value.notes ?? "").trim()) onChange({ notes: trimmed });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {RIDE_PREF_CHOICES.map((c) => (
        <div key={c.field}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
            <Icon name={c.icon} size={17} color="var(--silver)" />
            <span
              style={{
                fontSize: 13.5,
                color: "var(--arctic)",
                fontFamily: "var(--font-sans)",
                fontWeight: 500,
              }}
            >
              {t(c.label)}
            </span>
          </div>
          <ChoicePills
            value={value[c.field as keyof RidePreferences] as string}
            options={c.options}
            busy={busy}
            onPick={(v) => onChange({ [c.field]: v } as Partial<RidePreferences>)}
          />
        </div>
      ))}

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {RIDE_PREF_TOGGLES.map((tg) => (
          <div
            key={tg.field}
            style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0" }}
          >
            <Icon name={tg.icon} size={18} color="var(--silver)" />
            <span
              style={{ flex: 1, fontSize: 14, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}
            >
              {t(tg.label)}
            </span>
            <Toggle
              on={!!value[tg.field as keyof RidePreferences]}
              setOn={(v) => onChange({ [tg.field]: v } as Partial<RidePreferences>)}
            />
          </div>
        ))}
      </div>

      <label style={{ display: "block" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
          <Icon name="pencil" size={16} color="var(--silver)" />
          <span
            style={{
              fontSize: 13.5,
              color: "var(--arctic)",
              fontFamily: "var(--font-sans)",
              fontWeight: 500,
            }}
          >
            {t("acct.ridePrefs.notes")}
          </span>
        </div>
        <textarea
          value={notes}
          placeholder={t("acct.ridePrefs.notesPh")}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={commitNotes}
          maxLength={RIDE_NOTES_MAX}
          rows={3}
          style={{
            width: "100%",
            boxSizing: "border-box",
            resize: "vertical",
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            borderRadius: "var(--radius-md)",
            padding: "10px 12px",
            color: "var(--arctic)",
            fontSize: 13.5,
            fontFamily: "var(--font-sans)",
            outline: "none",
          }}
        />
        <div
          style={{
            fontSize: 11,
            color: "var(--fg3)",
            marginTop: 4,
            textAlign: "right",
            fontFamily: "var(--font-sans)",
          }}
        >
          {notes.length}/{RIDE_NOTES_MAX}
        </div>
      </label>
    </div>
  );
}
