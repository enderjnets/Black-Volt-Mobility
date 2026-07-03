"use client";

import { useCallback, useEffect, useState } from "react";

import { publicSiteOrigin } from "@/lib/tenant";
import { fetchMe } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import {
  AdminEvent,
  approveSuggestion,
  dismissSuggestion,
  EventSuggestion,
  generateEventPost,
  listAdminEvents,
  listSuggestions,
  patchEvent,
  scanNow,
} from "@/lib/events";
import { Button, Card, Field, Pill } from "../ui";
import { EventPricingPanel } from "./EventPricingPanel";
import { Icon } from "../Icon";

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function EventsAdmin() {
  const { t } = useI18n();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [tab, setTab] = useState<"suggestions" | "events">("suggestions");
  const [suggestions, setSuggestions] = useState<EventSuggestion[]>([]);
  const [events, setEvents] = useState<AdminEvent[]>([]);
  const [busy, setBusy] = useState<number | "scan" | null>(null);
  const [note, setNote] = useState<string>("");
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    fetchMe()
      .then((m) => setIsAdmin(!!m.is_admin || !m.auth_enabled))
      .catch(() => setIsAdmin(false));
  }, []);

  const reload = useCallback(async () => {
    setErr("");
    try {
      const [s, e] = await Promise.all([listSuggestions(), listAdminEvents()]);
      setSuggestions(s);
      setEvents(e);
    } catch (x) {
      setErr(String(x instanceof Error ? x.message : x));
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void reload();
  }, [isAdmin, reload]);

  if (isAdmin === null) return null;
  if (!isAdmin) {
    return (
      <div style={{ padding: 24, color: "var(--fg3)" }}>{t("dash.events.adminOnly")}</div>
    );
  }

  const runScan = async () => {
    setBusy("scan");
    setErr("");
    setNote("");
    try {
      const r = await scanNow();
      setNote(t("dash.events.scanResult", { created: r.created, updated: r.updated }));
      await reload();
    } catch (x) {
      setErr(String(x instanceof Error ? x.message : x));
    } finally {
      setBusy(null);
    }
  };

  const approve = async (s: EventSuggestion) => {
    setBusy(s.id);
    setErr("");
    setNote("");
    try {
      const ev = await approveSuggestion(s.id);
      setNote(t("dash.events.approved", { title: ev.title }));
      await reload();
      setTab("events");
    } catch (x) {
      setErr(String(x instanceof Error ? x.message : x));
    } finally {
      setBusy(null);
    }
  };

  const dismiss = async (s: EventSuggestion) => {
    setBusy(s.id);
    try {
      await dismissSuggestion(s.id);
      await reload();
    } catch (x) {
      setErr(String(x instanceof Error ? x.message : x));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 4px" }}>
      <div
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: 12, flexWrap: "wrap", marginBottom: 14,
        }}
      >
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("dash.events.title")}</h1>
        <Button onClick={runScan} disabled={busy === "scan"}>
          {busy === "scan" ? t("dash.events.scanning") : t("dash.events.scan")}
        </Button>
      </div>

      {note && (
        <div style={{ marginBottom: 12, color: "var(--volt)", fontSize: 13 }}>{note}</div>
      )}
      {err && (
        <div style={{ marginBottom: 12, color: "#ff6b6b", fontSize: 13 }}>{err}</div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["suggestions", "events"] as const).map((tb) => (
          <button
            key={tb}
            onClick={() => setTab(tb)}
            style={{
              padding: "8px 16px", borderRadius: "var(--radius-full)",
              border: "1px solid var(--line-strong)", cursor: "pointer",
              background: tab === tb ? "var(--volt)" : "transparent",
              color: tab === tb ? "var(--obsidian-3)" : "var(--silver)",
              fontWeight: 600, fontSize: 13,
            }}
          >
            {tb === "suggestions"
              ? `${t("dash.events.tab.suggestions")} (${suggestions.length})`
              : `${t("dash.events.tab.events")} (${events.length})`}
          </button>
        ))}
      </div>

      {tab === "suggestions" ? (
        suggestions.length === 0 ? (
          <div style={{ padding: 24, color: "var(--fg3)" }}>{t("dash.events.empty")}</div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {suggestions.map((s) => (
              <SuggestionCard
                key={s.id}
                s={s}
                busy={busy === s.id}
                onApprove={() => approve(s)}
                onDismiss={() => dismiss(s)}
              />
            ))}
          </div>
        )
      ) : events.length === 0 ? (
        <div style={{ padding: 24, color: "var(--fg3)" }}>{t("dash.events.emptyEvents")}</div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {events.map((e) => (
            <EventCard key={e.id} e={e} onChange={reload} />
          ))}
        </div>
      )}
    </div>
  );
}

function SuggestionCard({
  s, busy, onApprove, onDismiss,
}: {
  s: EventSuggestion;
  busy: boolean;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <div
          style={{
            width: 96, height: 96, borderRadius: 12, flexShrink: 0, overflow: "hidden",
            background: "linear-gradient(135deg, var(--obsidian-3), var(--volt))",
          }}
        >
          {s.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={s.image_url}
              alt=""
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          )}
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{s.title}</div>
          <div style={{ color: "var(--fg3)", fontSize: 13, marginTop: 2 }}>{s.venue_name}</div>
          <div style={{ color: "var(--silver)", fontSize: 13, marginTop: 2 }}>
            {fmtDate(s.starts_at)}
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
            <Pill tone="muted">{s.source}</Pill>
            {s.venue_key && <Pill tone="success">{s.venue_key}</Pill>}
            {s.score != null && <Pill tone="muted">{`score ${s.score.toFixed(2)}`}</Pill>}
            {s.distance_mi != null && (
              <Pill tone="muted">{`${s.distance_mi} mi`}</Pill>
            )}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <Button onClick={onApprove} disabled={busy}>
          {busy ? t("dash.events.approving") : t("dash.events.approve")}
        </Button>
        <Button variant="ghost" onClick={onDismiss} disabled={busy}>
          {t("dash.events.dismiss")}
        </Button>
      </div>
    </Card>
  );
}

function EventCard({ e, onChange }: { e: AdminEvent; onChange: () => void }) {
  const { t } = useI18n();
  const [title, setTitle] = useState(e.title);
  const [about, setAbout] = useState(e.about_text || "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const publicUrl = `${publicSiteOrigin()}/events/${e.slug}`;

  const save = async () => {
    setBusy(true);
    try {
      await patchEvent(e.id, { title, about_text: about });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onChange();
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status: string) => {
    setBusy(true);
    try {
      await patchEvent(e.id, { status });
      onChange();
    } finally {
      setBusy(false);
    }
  };

  const genPost = async (kind: "video" | "image") => {
    setBusy(true);
    try {
      await generateEventPost(e.id, kind);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <Pill tone={e.status === "published" ? "success" : e.status === "archived" ? "muted" : "warning"}>
          {e.status}
        </Pill>
        <a
          href={publicUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "var(--volt)", fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}
        >
          <Icon name="external-link" size={14} color="currentColor" />
          {t("dash.events.viewPublic")}
        </a>
      </div>
      <div style={{ marginTop: 10 }}>
        <Field label={t("dash.events.field.title")} value={title} onChange={setTitle} />
      </div>
      <div style={{ marginTop: 10 }}>
        <label style={{ fontSize: 12, color: "var(--fg3)", display: "block", marginBottom: 4 }}>
          {t("dash.events.field.about")}
        </label>
        <textarea
          value={about}
          onChange={(ev) => setAbout(ev.target.value)}
          rows={4}
          style={{
            width: "100%", padding: "10px 12px", borderRadius: 10,
            border: "1px solid var(--line-strong)", background: "transparent",
            color: "var(--silver)", fontSize: 13, resize: "vertical",
          }}
        />
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <Button onClick={save} disabled={busy}>
          {saved ? t("dash.events.saved") : t("dash.events.save")}
        </Button>
        {e.status === "published" ? (
          <Button variant="ghost" onClick={() => setStatus("draft")} disabled={busy}>
            {t("dash.events.unpublish")}
          </Button>
        ) : (
          <Button variant="ghost" onClick={() => setStatus("published")} disabled={busy}>
            {t("dash.events.publish")}
          </Button>
        )}
        <Button variant="ghost" onClick={() => setStatus("archived")} disabled={busy}>
          {t("dash.events.archive")}
        </Button>
        <Button variant="ghost" onClick={() => genPost("video")} disabled={busy}>
          {t("dash.events.generate.video")}
        </Button>
        <Button variant="ghost" onClick={() => genPost("image")} disabled={busy}>
          {t("dash.events.generate.photo")}
        </Button>
      </div>
      <EventPricingPanel e={e} />
    </Card>
  );
}
