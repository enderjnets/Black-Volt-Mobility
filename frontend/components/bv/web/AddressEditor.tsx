/* Add / edit a saved address. Modal mirrors ProfileGate's chrome (fixed overlay,
   branded card, scrolls on small screens). Reuses the booking AddressField so
   the address input has the same Google Places autocomplete as /book. */
"use client";

import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import { createAddress, updateAddress, type SavedAddress } from "@/lib/addresses";
import { Icon } from "../Icon";
import { AddressField } from "./AddressField";

export function AddressEditor({
  initial,
  onClose,
  onSaved,
}: {
  initial?: SavedAddress;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [label, setLabel] = useState(initial?.label ?? "");
  const [address, setAddress] = useState(initial?.address ?? "");
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);
  const [labelFocus, setLabelFocus] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = address.trim() !== "" && !saving;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const body = {
        label: label.trim() || null,
        address: address.trim(),
        is_default: isDefault,
      };
      if (initial) await updateAddress(initial.id, body);
      else await createAddress(body);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
      setSaving(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={initial ? t("acct.addr.editTitle") : t("acct.addr.addTitle")}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(5,5,9,0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          maxHeight: "calc(100dvh - 32px)",
          overflowY: "auto",
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-volt)",
          padding: 24,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <h2 style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: 22, color: "var(--arctic)" }}>
            {initial ? t("acct.addr.editTitle") : t("acct.addr.addTitle")}
          </h2>
          <button
            onClick={onClose}
            aria-label={t("gate.close")}
            style={{ background: "transparent", border: "none", cursor: "pointer", padding: 4 }}
          >
            <Icon name="x" size={20} color="var(--silver)" />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 20 }}>
          <label style={{ display: "block" }}>
            <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7, fontFamily: "var(--font-sans)" }}>
              {t("acct.addr.label")}
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                background: "var(--obsidian-3)",
                borderRadius: "var(--radius-md)",
                padding: "12px 14px",
                border: `1px solid ${labelFocus ? "var(--volt)" : "var(--line-strong)"}`,
              }}
            >
              <Icon name="pencil" size={18} color={labelFocus ? "var(--volt)" : "var(--silver)"} />
              <input
                value={label}
                placeholder={t("acct.addr.labelPh")}
                onChange={(e) => setLabel(e.target.value)}
                onFocus={() => setLabelFocus(true)}
                onBlur={() => setLabelFocus(false)}
                maxLength={80}
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

          <AddressField
            icon="map-pin"
            label={t("acct.addr.address")}
            value={address}
            placeholder={t("gate.address.ph")}
            onChange={setAddress}
          />

          <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              style={{ accentColor: "var(--volt)", width: 16, height: 16 }}
            />
            <span style={{ fontSize: 13, color: "var(--silver)", fontFamily: "var(--font-sans)" }}>
              {t("acct.addr.makeDefault")}
            </span>
          </label>

          {error && (
            <div style={{ fontSize: 13, color: "var(--danger)", fontFamily: "var(--font-sans)" }}>{error}</div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
            <button
              onClick={onClose}
              style={{
                flex: 1,
                padding: "13px 18px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--line-strong)",
                cursor: "pointer",
                background: "var(--obsidian-3)",
                color: "var(--silver)",
                fontFamily: "var(--font-display)",
                fontSize: 15,
                fontWeight: 600,
              }}
            >
              {t("acct.addr.cancel")}
            </button>
            <button
              onClick={save}
              disabled={!canSave}
              style={{
                flex: 1,
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
              {saving ? t("acct.addr.saving") : t("acct.addr.save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
