/* Onboarding profile gate. Shown right after Google sign-in when the passenger's
   profile is incomplete (missing first/last name or phone) — the data Google
   can't give us. Blocks the booking until completed; dismissing cancels.
   Mobile-first: the card fills small screens and centers on tablet/desktop. */
"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";
import {
  defaultRidePreferences,
  getProfile,
  looksLikePhone,
  updateProfile,
  type RidePreferences,
} from "@/lib/profile";
import { Icon } from "../Icon";
import { AddressField } from "./AddressField";
import { RidePreferencesFields } from "./RidePreferences";

function Field({
  label, icon, value, onChange, placeholder, type = "text", inputMode, required,
}: {
  label: string;
  icon: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  inputMode?: "text" | "tel";
  required?: boolean;
}) {
  const [focus, setFocus] = useState(false);
  return (
    <label style={{ display: "block" }}>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7, fontFamily: "var(--font-sans)" }}>
        {label}
        {required && <span style={{ color: "var(--volt)" }}> *</span>}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "var(--obsidian-3)",
          borderRadius: "var(--radius-md)",
          padding: "12px 14px",
          border: `1px solid ${focus ? "var(--volt)" : "var(--line-strong)"}`,
        }}
      >
        <Icon name={icon} size={18} color={focus ? "var(--volt)" : "var(--silver)"} />
        <input
          type={type}
          inputMode={inputMode}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocus(true)}
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
    </label>
  );
}

export function ProfileGate({ onSaved, onClose }: { onSaved: () => void; onClose: () => void }) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [sms, setSms] = useState(false);
  const [prefs, setPrefs] = useState<RidePreferences>(defaultRidePreferences());
  const [showPrefs, setShowPrefs] = useState(false);

  useEffect(() => {
    let alive = true;
    getProfile()
      .then((p) => {
        if (!alive) return;
        setFirst(p.first_name || "");
        setLast(p.last_name || "");
        setPhone(p.phone || "");
        setAddress(p.home_address || "");
        setSms(p.sms_consent);
        setPrefs(p.ride_preferences ?? defaultRidePreferences());
      })
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const phoneOk = looksLikePhone(phone);
  const canSave = first.trim() !== "" && last.trim() !== "" && phoneOk && !saving;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await updateProfile({
        first_name: first.trim(),
        last_name: last.trim(),
        phone: phone.trim(),
        home_address: address.trim(),
        sms_consent: sms,
        ride_preferences: prefs,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("gate.error"));
      setSaving(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("gate.title")}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(5,5,9,0.72)",
        display: "flex",
        justifyContent: "center",
        // Scroll on the overlay (not the card) so the address autocomplete dropdown
        // isn't clipped by the card's overflow; margin:auto centers it when it fits.
        overflowY: "auto",
        padding: "24px 16px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          margin: "auto",
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-volt)",
          padding: 24,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <h2 style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: 22, color: "var(--arctic)" }}>
              {t("gate.title")}
            </h2>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--fg3)", fontFamily: "var(--font-sans)" }}>
              {t("gate.subtitle")}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label={t("gate.close")}
            style={{ background: "transparent", border: "none", cursor: "pointer", padding: 4 }}
          >
            <Icon name="x" size={20} color="var(--silver)" />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 20 }}>
          <Field label={t("gate.first")} icon="user" value={first} onChange={setFirst} required />
          <Field label={t("gate.last")} icon="user" value={last} onChange={setLast} required />
          <div>
            <Field
              label={t("gate.phone")}
              icon="phone"
              value={phone}
              onChange={setPhone}
              placeholder={t("gate.phone.ph")}
              type="tel"
              inputMode="tel"
              required
            />
            {phone.trim() !== "" && !phoneOk && (
              <div style={{ fontSize: 12, color: "var(--danger)", marginTop: 6, fontFamily: "var(--font-sans)" }}>
                {t("gate.phone.invalid")}
              </div>
            )}
          </div>
          <AddressField
            icon="map-pin"
            label={t("gate.address")}
            value={address}
            placeholder={t("gate.address.ph")}
            onChange={setAddress}
          />
          <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={sms}
              onChange={(e) => setSms(e.target.checked)}
              style={{ marginTop: 2, accentColor: "var(--volt)", width: 16, height: 16 }}
            />
            <span style={{ fontSize: 13, color: "var(--silver)", fontFamily: "var(--font-sans)" }}>
              {t("gate.sms")}
            </span>
          </label>

          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <button
              type="button"
              onClick={() => setShowPrefs((s) => !s)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                padding: 0,
                color: "var(--silver)",
                fontFamily: "var(--font-sans)",
                fontSize: 13,
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Icon name="settings" size={16} color="var(--silver)" />
                {t("gate.prefs.toggle")}
              </span>
              <Icon name={showPrefs ? "chevron-up" : "chevron-down"} size={16} color="var(--silver)" />
            </button>
            {showPrefs && (
              <div style={{ marginTop: 14 }}>
                <RidePreferencesFields
                  value={prefs}
                  onChange={(patch) => setPrefs((cur) => ({ ...cur, ...patch }))}
                />
              </div>
            )}
          </div>

          {error && (
            <div style={{ fontSize: 13, color: "var(--danger)", fontFamily: "var(--font-sans)" }}>{error}</div>
          )}

          <button
            onClick={save}
            disabled={!canSave}
            style={{
              marginTop: 4,
              padding: "13px 18px",
              borderRadius: "var(--radius-md)",
              border: "none",
              cursor: canSave ? "pointer" : "not-allowed",
              opacity: canSave ? 1 : 0.5,
              background: "var(--volt)",
              color: "var(--void)",
              fontFamily: "var(--font-display)",
              fontSize: 15,
              fontWeight: 600,
            }}
          >
            {saving ? t("gate.saving") : t("gate.save")}
          </button>
          {loading && (
            <div style={{ fontSize: 12, color: "var(--fg3)", textAlign: "center", fontFamily: "var(--font-sans)" }}>
              {t("gate.loading")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
