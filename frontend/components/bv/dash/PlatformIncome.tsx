"use client";

/* Platform income — upload an Uber/Lyft/Co-op earnings screenshot, the AI reads
   it (trips / earnings / hours / period), the driver reviews and saves it. Shows
   platform income over time and a platform-vs-private comparison — the whole
   pitch: convert those gig riders into higher-margin private clients. Does NOT
   touch the sales funnel. */

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  type Platform,
  type PlatformDraft,
  type PlatformSummary,
  deletePlatform,
  extractPlatform,
  getPlatformSummary,
  savePlatform,
} from "@/lib/platform";

const PLATFORMS: Platform[] = ["uber", "lyft", "coop", "other"];

function money(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

function Num({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  step?: number;
}) {
  return (
    <label style={{ flex: 1, minWidth: 90, display: "flex", flexDirection: "column", gap: 5 }}>
      <span style={{ fontSize: 12, color: "var(--silver)", fontWeight: 600 }}>{label}</span>
      <input
        type="number"
        min={0}
        step={step ?? 1}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Math.max(0, Number(e.target.value)))}
        style={{
          width: "100%",
          background: "var(--obsidian-2)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: "9px 11px",
          color: "var(--arctic)",
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 17,
        }}
      />
    </label>
  );
}

export function PlatformIncome({ days }: { days: number }) {
  const { t } = useI18n();
  const [data, setData] = useState<PlatformSummary | null>(null);
  const [draft, setDraft] = useState<PlatformDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [simulated, setSimulated] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(
    () => getPlatformSummary(days).then(setData).catch(() => {}),
    [days],
  );
  useEffect(() => {
    load();
  }, [load]);

  const onFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (fileRef.current) fileRef.current.value = "";
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await extractPlatform(files);
      setSimulated(res.simulated);
      setDraft(res.fields);
    } catch (ex) {
      setErr((ex as Error)?.message === "subscription_required" ? "sub" : "extract");
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = async () => {
    if (!draft) return;
    setBusy(true);
    setErr(null);
    try {
      await savePlatform({
        platform: draft.platform || "other",
        period_label: draft.period_label,
        period_start: draft.period_start,
        period_end: draft.period_end,
        trips: draft.trips,
        earnings: draft.earnings,
        online_hours: draft.online_hours,
        currency: draft.currency,
      });
      setDraft(null);
      await load();
    } catch {
      setErr("save");
    } finally {
      setBusy(false);
    }
  };

  const patch = (p: Partial<PlatformDraft>) => setDraft((d) => (d ? { ...d, ...p } : d));

  const cmp = data?.comparison;
  const total = (cmp?.platform || 0) + (cmp?.private || 0);

  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Icon name="upload" size={16} color="var(--volt)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>
          {t("dash.stats.plat.title")}
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--fg3)", marginBottom: 14 }}>{t("dash.stats.plat.hint")}</div>

      {/* Upload */}
      {!draft && (
        <div style={{ marginBottom: 16 }}>
          <input ref={fileRef} type="file" accept="image/*" multiple onChange={onFiles} style={{ display: "none" }} />
          <Button variant="solid" icon="upload" disabled={busy} onClick={() => fileRef.current?.click()}>
            {busy ? t("dash.stats.plat.reading") : t("dash.stats.plat.upload")}
          </Button>
          {err === "sub" && (
            <div style={{ fontSize: 12.5, color: "var(--warning)", marginTop: 10, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="circle-dot" size={13} color="var(--warning)" />
              {t("dash.stats.plat.subRequired")}
            </div>
          )}
          {err === "extract" && (
            <div style={{ fontSize: 12.5, color: "var(--danger)", marginTop: 10 }}>{t("dash.stats.plat.extractErr")}</div>
          )}
        </div>
      )}

      {/* Review draft */}
      {draft && (
        <div style={{ background: "var(--obsidian-2)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-md)", padding: 14, marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: "var(--arctic)", fontWeight: 600, marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="sparkles" size={14} color="var(--volt)" />
            {t("dash.stats.plat.review")}
            {simulated && <span style={{ fontSize: 11, color: "var(--fg3)" }}>· {t("dash.stats.plat.demo")}</span>}
          </div>
          {/* platform segmented */}
          <div style={{ display: "flex", gap: 4, background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 4, marginBottom: 12, width: "fit-content" }}>
            {PLATFORMS.map((p) => (
              <button
                key={p}
                onClick={() => patch({ platform: p })}
                style={{
                  padding: "6px 13px",
                  borderRadius: "var(--radius-full)",
                  cursor: "pointer",
                  fontSize: 12.5,
                  fontWeight: 600,
                  border: "none",
                  textTransform: "capitalize",
                  background: draft.platform === p ? "var(--volt-bg-20)" : "transparent",
                  color: draft.platform === p ? "var(--volt)" : "var(--silver)",
                  boxShadow: draft.platform === p ? "inset 0 0 0 1px var(--volt-border)" : "none",
                }}
              >
                {t(`dash.stats.plat.app.${p}`)}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            <label style={{ flex: 2, minWidth: 140, display: "flex", flexDirection: "column", gap: 5 }}>
              <span style={{ fontSize: 12, color: "var(--silver)", fontWeight: 600 }}>{t("dash.stats.plat.period")}</span>
              <input
                value={draft.period_label || ""}
                onChange={(e) => patch({ period_label: e.target.value })}
                placeholder="Jun 9 – 15"
                style={{ width: "100%", background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: "9px 11px", color: "var(--arctic)", fontSize: 14 }}
              />
            </label>
            <label style={{ flex: 1, minWidth: 130, display: "flex", flexDirection: "column", gap: 5 }}>
              <span style={{ fontSize: 12, color: "var(--silver)", fontWeight: 600 }}>{t("dash.stats.plat.periodEnd")}</span>
              <input
                type="date"
                value={draft.period_end || ""}
                onChange={(e) => patch({ period_end: e.target.value || null })}
                style={{ width: "100%", background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: "9px 11px", color: "var(--arctic)", fontSize: 14 }}
              />
            </label>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
            <Num label={t("dash.stats.plat.trips")} value={draft.trips} onChange={(v) => patch({ trips: v })} />
            <Num label={t("dash.stats.plat.earnings")} value={draft.earnings} onChange={(v) => patch({ earnings: v })} step={0.01} />
            <Num label={t("dash.stats.plat.hours")} value={draft.online_hours} onChange={(v) => patch({ online_hours: v })} step={0.1} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="solid" icon="circle-check" disabled={busy} onClick={saveDraft}>
              {busy ? t("dash.stats.saving") : t("dash.stats.plat.save")}
            </Button>
            <Button variant="ghost" icon="x" disabled={busy} onClick={() => setDraft(null)}>
              {t("dash.stats.plat.discard")}
            </Button>
          </div>
          {err === "save" && <div style={{ fontSize: 12.5, color: "var(--danger)", marginTop: 8 }}>{t("dash.stats.plat.saveErr")}</div>}
        </div>
      )}

      {/* Comparison */}
      {data && (cmp?.platform || cmp?.private) ? (
        <div style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
            <span style={{ color: "var(--silver)" }}>
              {t("dash.stats.plat.private")} <b style={{ color: "var(--volt)" }}>{money(cmp!.private)}</b>
            </span>
            <span style={{ color: "var(--silver)" }}>
              {t("dash.stats.plat.platform")} <b style={{ color: "var(--arctic)" }}>{money(cmp!.platform)}</b>
            </span>
          </div>
          <div style={{ display: "flex", height: 12, borderRadius: 99, overflow: "hidden", background: "var(--obsidian-3)" }}>
            <div style={{ width: `${total > 0 ? (cmp!.private / total) * 100 : 0}%`, background: "var(--volt)" }} />
            <div style={{ flex: 1, background: "var(--obsidian-3)" }} />
          </div>
          <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 8 }}>
            {cmp!.private_share !== null
              ? t("dash.stats.plat.share", { p: `${Math.round(cmp!.private_share * 100)}%` })
              : t("dash.stats.plat.shareNone")}
            {data.totals.per_trip ? ` · ${t("dash.stats.plat.perTrip", { v: money(data.totals.per_trip) })}` : ""}
          </div>
        </div>
      ) : null}

      {/* Imports list */}
      {data && data.imports.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 7, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          {data.imports.map((s) => (
            <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
              <span style={{ textTransform: "capitalize", color: "var(--arctic)", fontWeight: 600, width: 56 }}>{t(`dash.stats.plat.app.${s.platform}`)}</span>
              <span style={{ color: "var(--fg3)", flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.period_label || s.period_end || "—"}</span>
              <span style={{ color: "var(--silver)" }}>{s.trips ?? "—"} {t("dash.stats.plat.tripsShort")}</span>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--arctic)", width: 70, textAlign: "right" }}>{s.earnings != null ? money(s.earnings) : "—"}</span>
              <button onClick={() => deletePlatform(s.id).then(load)} aria-label="Delete" style={{ background: "none", border: "none", cursor: "pointer", padding: 4, color: "var(--fg3)" }}>
                <Icon name="trash-2" size={14} color="var(--fg3)" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
