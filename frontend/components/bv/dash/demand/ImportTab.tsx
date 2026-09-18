"use client";

/* Upload the Uber data export ZIP and show exactly what came in — and what did
   not, with the consequence, so the owner knows what the model can learn from.
   Addendum A (2026-09-17): when the export carries phone GPS history, also
   show where the month's waits actually happened. */

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import { type GpsSummary, type ImportSummary, getImportStatus, importZip } from "@/lib/demand";

type Phase = "idle" | "uploading" | "processing" | "done" | "error";

function WaitLabel({ w, t }: { w: GpsSummary["top_waits"][number]; t: (key: string) => string }) {
  if (w.place) {
    return (
      <>
        {w.place}
        {w.distance_km != null && (
          <span style={{ color: "var(--silver)" }}> ({w.distance_km.toFixed(1)} km)</span>
        )}
      </>
    );
  }
  if (w.zone_name) return <>{w.zone_name}</>;
  if (w.outside) return <>{t("dash.demand.import.gps.outside")}</>;
  return <>{t("dash.demand.import.gps.other")}</>;
}

export function ImportTab() {
  const { t } = useI18n();
  const [phase, setPhase] = useState<Phase>("idle");
  const [pct, setPct] = useState(0);
  const [summary, setSummary] = useState<(ImportSummary & { at?: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  // A second drop/pick while the first upload is still in flight must not start
  // a race against it — same guard LogTab uses for its buttons while busy.
  const busy = phase === "uploading" || phase === "processing";

  useEffect(() => {
    getImportStatus()
      .then((s) => {
        if (!("never" in s)) setSummary(s);
      })
      .catch(() => {});
  }, []);

  const run = useCallback(
    async (file: File) => {
      setError(null);
      setPhase("uploading");
      setPct(0);
      try {
        const s = await importZip(file, (p) => {
          setPct(p);
          if (p >= 100) setPhase("processing");
        });
        setSummary({ ...s, at: new Date().toISOString() });
        setPhase("done");
      } catch (e) {
        const code = (e as { message?: string })?.message || "";
        const key = ["not_a_zip", "no_csv", "too_large"].includes(code)
          ? `dash.demand.import.err.${code}`
          : "dash.demand.import.err.generic";
        setError(t(key));
        setPhase("error");
      }
    },
    [t],
  );

  const onFiles = (files: FileList | null) => {
    if (busy) return;
    const f = files?.[0];
    if (f) run(f);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 16, fontWeight: 700 }}>{t("dash.demand.import.title")}</div>
      <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.import.help")}</div>

      <div
        onDragOver={(e) => { e.preventDefault(); if (!busy) setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }}
        onClick={() => { if (!busy) input.current?.click(); }}
        style={{ minHeight: 120, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 14, border: `2px dashed ${drag ? "var(--volt)" : "var(--line-strong)"}`, background: drag ? "rgba(0,229,255,0.06)" : "var(--obsidian)", cursor: busy ? "default" : "pointer", fontSize: 14 }}
      >
        <Icon name="upload" size={24} color="var(--volt)" />
        {phase === "uploading" ? `${t("dash.demand.import.uploading")} ${pct}%`
          : phase === "processing" ? t("dash.demand.import.processing")
          : t("dash.demand.import.drop")}
        <input ref={input} type="file" accept=".zip,application/zip" style={{ display: "none" }} onChange={(e) => onFiles(e.target.files)} disabled={busy} />
      </div>
      {(phase === "uploading" || phase === "processing") && (
        <div style={{ height: 6, borderRadius: 3, background: "var(--line-strong)" }}>
          <div style={{ width: `${phase === "processing" ? 100 : pct}%`, height: "100%", borderRadius: 3, background: "var(--volt)", transition: "width .2s" }} />
        </div>
      )}
      {error && <div style={{ color: "#ff7a7a", fontSize: 13 }}><Icon name="alert-circle" size={14} color="currentColor" /> {error}</div>}

      {summary && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 12, borderRadius: 12, border: "1px solid var(--line-strong)", background: "var(--obsidian)", fontSize: 13 }}>
          <div style={{ fontWeight: 700 }}>
            {phase === "done" ? t("dash.demand.import.done") : t("dash.demand.import.last")}
            {summary.at ? ` · ${new Date(summary.at).toLocaleString()}` : ""}
          </div>
          <Row label={t("dash.demand.import.trips")} a={summary.trips.inserted} b={summary.trips.skipped} t={t} />
          <Row label={t("dash.demand.import.segments")} a={summary.segments.inserted} b={summary.segments.skipped} t={t} />
          <Row label={t("dash.demand.import.windows")} a={summary.windows.inserted} b={summary.windows.skipped} t={t} />
          {summary.trips.date_min && (
            <div><span style={{ color: "var(--silver)" }}>{t("dash.demand.import.range")}:</span> {summary.trips.date_min.slice(0, 10)} → {summary.trips.date_max?.slice(0, 10)}</div>
          )}
          {Object.keys(summary.trips.by_product).length > 0 && (
            <div><span style={{ color: "var(--silver)" }}>{t("dash.demand.import.byProduct")}:</span> {Object.entries(summary.trips.by_product).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
          )}
          <div><span style={{ color: "var(--silver)" }}>{t("dash.demand.import.found")}:</span> {summary.files_found.join(", ") || "—"}</div>
          {summary.files_missing.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ color: "#ff7a7a", fontWeight: 700 }}>{t("dash.demand.import.missing")}</div>
              {summary.files_missing.map((m) => (
                <div key={m.kind} style={{ color: "#ff9a9a" }}>• {m.consequence}</div>
              ))}
            </div>
          )}
          {summary.gps && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontWeight: 700 }}>{t("dash.demand.import.gps.title")}</div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ color: "var(--silver)", textAlign: "left" }}>
                      <th style={{ padding: "4px 6px" }}>{t("dash.demand.import.gps.col.place")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.demand.import.gps.col.hours")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.demand.import.gps.col.premium")}</th>
                      <th style={{ padding: "4px 6px" }}>{t("dash.demand.import.gps.col.perHour")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.gps.top_waits.map((w) => (
                      <tr key={w.h3_r8} style={{ borderTop: "1px solid var(--line-strong)" }}>
                        <td style={{ padding: "4px 6px" }}><WaitLabel w={w} t={t} /></td>
                        <td style={{ padding: "4px 6px" }}>{w.hours.toFixed(1)} h</td>
                        <td style={{ padding: "4px 6px" }}>{w.premium_requests}</td>
                        <td style={{ padding: "4px 6px" }}>{w.per_hour.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize: 11, color: "var(--silver)" }}>
                {t("dash.demand.import.gps.summary", {
                  days: summary.gps.days,
                  pings: summary.gps.pings,
                  home_hours: summary.gps.home_hours.toFixed(1),
                })}
              </div>
            </div>
          )}
        </div>
      )}
      {!summary && phase === "idle" && <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.import.never")}</div>}
    </div>
  );
}

function Row({ label, a, b, t }: { label: string; a: number; b: number; t: (k: string) => string }) {
  return (
    <div>
      <span style={{ color: "var(--silver)" }}>{label}:</span> {a} {t("dash.demand.import.inserted")} · {b} {t("dash.demand.import.skipped")}
    </div>
  );
}
