"use client";

/* Discount-codes panel (all drivers). Create, toggle and delete promo codes
   that clients can apply at booking. Mirrors the dark dashboard card style of
   Team/Rates. Backend: GET/POST /v1/discounts, PATCH/DELETE /v1/discounts/{id}. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Toggle } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  createDiscount,
  deleteDiscount,
  listDiscounts,
  patchDiscount,
  type DiscountCode,
} from "@/lib/discounts";

// 422 detail slugs the backend may return
const KNOWN_ERRS = new Set([
  "discount_pct_exceeds_driver_cap",
  "code_already_exists",
  "invalid_code",
]);

function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

function generateCode(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let suffix = "";
  for (let i = 0; i < 6; i++) suffix += chars[Math.floor(Math.random() * chars.length)];
  return `BV-${suffix}`;
}

export function Discounts() {
  const { t } = useI18n();
  const [rows, setRows] = useState<DiscountCode[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  // Create form state
  const [code, setCode] = useState("");
  const [pct, setPct] = useState<number | "">(10);
  const [maxUses, setMaxUses] = useState<number | "">("");
  const [expiresAt, setExpiresAt] = useState("");
  const [creating, setCreating] = useState(false);

  const errText = (e: unknown): string => {
    const c = e instanceof Error ? e.message : "";
    return t(KNOWN_ERRS.has(c) ? `dash.discounts.err.${c}` : "dash.discounts.err.generic");
  };

  const load = () =>
    listDiscounts()
      .then(setRows)
      .catch((e) => setErr(errText(e)));

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim() || creating) return;
    setCreating(true);
    setErr(null);
    setFlash(null);
    try {
      await createDiscount({
        code: code.trim().toUpperCase(),
        discount_pct: Number(pct) || 0,
        max_uses: maxUses !== "" ? Number(maxUses) : null,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
      setCode("");
      setPct(10);
      setMaxUses("");
      setExpiresAt("");
      setFlash(t("dash.discounts.created"));
      setTimeout(() => setFlash(null), 3000);
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setCreating(false);
    }
  };

  const toggle = async (row: DiscountCode) => {
    if (busy !== null) return;
    setBusy(row.id);
    setErr(null);
    setFlash(null);
    try {
      await patchDiscount(row.id, !row.active);
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (row: DiscountCode) => {
    if (!window.confirm(`${t("dash.discounts.deleteConfirm")} ${row.code}`)) return;
    if (busy !== null) return;
    setBusy(row.id);
    setErr(null);
    setFlash(null);
    try {
      await deleteDiscount(row.id);
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 18, maxWidth: 720 }}>
      <p style={{ fontSize: 13.5, color: "var(--silver)", margin: 0, lineHeight: 1.55 }}>
        {t("dash.discounts.subtitle")}
      </p>

      {/* Create form */}
      <form
        onSubmit={create}
        style={{
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          padding: 18,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {/* Code + Generate row */}
        <div className="bv-discount-fields" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div
            style={{
              flex: "1 1 200px",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--obsidian-3)",
              borderRadius: "var(--radius-md)",
              padding: "9px 11px",
              border: "1px solid var(--line-strong)",
              minWidth: 0,
            }}
          >
            <Icon name="tag" size={15} color="var(--silver)" />
            <input
              type="text"
              value={code}
              placeholder={t("dash.discounts.codePh")}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              style={{
                flex: 1,
                minWidth: 0,
                background: "transparent",
                border: "none",
                outline: "none",
                color: "var(--arctic)",
                fontSize: 13.5,
                fontFamily: "var(--font-sans)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            />
          </div>
          <button
            type="button"
            onClick={() => setCode(generateCode())}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "9px 13px",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 600,
              fontFamily: "var(--font-sans)",
              background: "var(--obsidian-3)",
              color: "var(--volt)",
              border: "1px solid var(--volt-border)",
              whiteSpace: "nowrap",
            }}
          >
            <Icon name="shuffle" size={14} color="currentColor" />
            {t("dash.discounts.generate")}
          </button>
        </div>

        {/* Numeric + expiry fields */}
        <div className="bv-discount-fields" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <DiscountField
            icon="percent"
            placeholder={t("dash.discounts.pctPh")}
            value={pct}
            onChange={setPct}
            min={1}
            max={100}
          />
          <DiscountField
            icon="hash"
            placeholder={t("dash.discounts.maxUsesPh")}
            value={maxUses}
            onChange={setMaxUses}
            min={1}
          />
          <div
            style={{
              flex: "1 1 180px",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--obsidian-3)",
              borderRadius: "var(--radius-md)",
              padding: "9px 11px",
              border: "1px solid var(--line-strong)",
              minWidth: 0,
            }}
          >
            <Icon name="calendar" size={15} color="var(--silver)" />
            <input
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              style={{
                flex: 1,
                minWidth: 0,
                background: "transparent",
                border: "none",
                outline: "none",
                color: expiresAt ? "var(--arctic)" : "var(--fg3)",
                fontSize: 13.5,
                fontFamily: "var(--font-sans)",
                colorScheme: "dark",
              }}
            />
          </div>
        </div>

        {/* Submit + cap hint */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <Button
            variant="solid"
            icon="plus"
            disabled={creating || !code.trim()}
            onClick={() => undefined}
          >
            {creating ? t("dash.discounts.creating") : t("dash.discounts.create")}
          </Button>
          <span style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.discounts.capHint")}</span>
        </div>
      </form>

      {/* Flash / error banners */}
      {flash && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "rgba(43,212,160,0.08)",
            border: "1px solid rgba(43,212,160,0.4)",
            borderRadius: "var(--radius-md)",
            padding: "10px 13px",
          }}
        >
          <Icon name="circle-check" size={15} color="var(--success)" />
          <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{flash}</span>
        </div>
      )}
      {err && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "rgba(255,92,110,0.08)",
            border: "1px solid rgba(255,92,110,0.4)",
            borderRadius: "var(--radius-md)",
            padding: "10px 13px",
          }}
        >
          <Icon name="alert-circle" size={15} color="var(--danger)" />
          <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{err}</span>
        </div>
      )}

      {/* Code list */}
      <div
        style={{
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
        }}
      >
        {rows === null ? (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
            {t("common.loading")}
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
            {t("dash.discounts.empty")}
          </div>
        ) : (
          <>
            {/* Column headers */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 72px 88px 110px 72px 40px",
                gap: 8,
                padding: "9px 16px",
                borderBottom: "1px solid var(--line)",
                fontSize: 11,
                fontWeight: 700,
                color: "var(--fg3)",
                textTransform: "uppercase",
                letterSpacing: "0.09em",
                fontFamily: "var(--font-sans)",
              }}
            >
              <span>{t("dash.discounts.col.code")}</span>
              <span>{t("dash.discounts.col.pct")}</span>
              <span>{t("dash.discounts.col.uses")}</span>
              <span>{t("dash.discounts.col.expiry")}</span>
              <span>{t("dash.discounts.col.active")}</span>
              <span />
            </div>
            {rows.map((row) => (
              <CodeRow
                key={row.id}
                row={row}
                busy={busy === row.id}
                onToggle={() => toggle(row)}
                onDelete={() => remove(row)}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function DiscountField({
  icon,
  placeholder,
  value,
  onChange,
  min,
  max,
}: {
  icon: string;
  placeholder: string;
  value: number | "";
  onChange: (v: number | "") => void;
  min?: number;
  max?: number;
}) {
  return (
    <div
      style={{
        flex: "1 1 130px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: "var(--obsidian-3)",
        borderRadius: "var(--radius-md)",
        padding: "9px 11px",
        border: "1px solid var(--line-strong)",
        minWidth: 0,
      }}
    >
      <Icon name={icon} size={15} color="var(--silver)" />
      <input
        type="number"
        value={value}
        placeholder={placeholder}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        style={{
          flex: 1,
          minWidth: 0,
          background: "transparent",
          border: "none",
          outline: "none",
          color: "var(--arctic)",
          fontSize: 13.5,
          fontFamily: "var(--font-sans)",
        }}
      />
    </div>
  );
}

function CodeRow({
  row,
  busy,
  onToggle,
  onDelete,
}: {
  row: DiscountCode;
  busy: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const expiry = fmtDate(row.expires_at);
  const isExpired = row.expires_at ? new Date(row.expires_at) < new Date() : false;
  const maxed = row.max_uses !== null && row.uses >= row.max_uses;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 72px 88px 110px 72px 40px",
        gap: 8,
        alignItems: "center",
        padding: "12px 16px",
        borderBottom: "1px solid var(--line)",
        opacity: busy ? 0.6 : 1,
        transition: "opacity .15s",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 14,
          color: "var(--arctic)",
          letterSpacing: "0.05em",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {row.code}
      </span>
      <span
        style={{
          fontSize: 14,
          fontWeight: 700,
          color: "var(--volt)",
          fontFamily: "var(--font-display)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {row.discount_pct}%
      </span>
      <span
        style={{
          fontSize: 13,
          color: maxed ? "var(--danger)" : "var(--silver)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {row.uses}
        {row.max_uses !== null ? `/${row.max_uses}` : ""}
      </span>
      <span style={{ fontSize: 12, color: isExpired ? "var(--danger)" : "var(--fg3)", whiteSpace: "nowrap" }}>
        {expiry ?? t("dash.discounts.noExpiry")}
      </span>
      <div>
        <Toggle on={row.active} setOn={() => onToggle()} />
      </div>
      <button
        onClick={onDelete}
        disabled={busy}
        title={t("dash.discounts.delete")}
        aria-label={t("dash.discounts.delete")}
        style={{
          background: "none",
          border: "none",
          cursor: busy ? "default" : "pointer",
          padding: 4,
          display: "flex",
          color: "var(--fg3)",
        }}
      >
        <Icon name="x" size={16} color="currentColor" />
      </button>
    </div>
  );
}
