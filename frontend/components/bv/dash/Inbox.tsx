"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  type ChatThread,
  type ChatThreadDetail,
  closeThread,
  getThread,
  listThreads,
} from "@/lib/chat";

type Filter = "all" | "open" | "escalated";

function relTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 604800) return `${Math.floor(s / 86400)}d`;
  return new Date(iso).toLocaleDateString();
}

export function Inbox() {
  const { t } = useI18n();
  const [filter, setFilter] = useState<Filter>("all");
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ChatThreadDetail | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listThreads(filter === "all" ? undefined : filter);
      setThreads(list);
    } catch {
      setThreads([]);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const open = async (id: number) => {
    setActiveId(id);
    try {
      const d = await getThread(id);
      setDetail(d);
      // opening clears the unread badge server-side; reflect it locally
      setThreads((ts) => ts.map((x) => (x.id === id ? { ...x, unread: 0 } : x)));
    } catch {
      setDetail(null);
    }
  };

  const doClose = async () => {
    if (activeId == null) return;
    try {
      await closeThread(activeId);
      await refresh();
      setDetail((d) => (d ? { ...d, status: "closed" } : d));
    } catch {
      /* ignore */
    }
  };

  const filters: Filter[] = ["all", "open", "escalated"];
  const filterLabel: Record<Filter, string> = {
    all: t("dash.inbox.filterAll"),
    open: t("dash.inbox.filterOpen"),
    escalated: t("dash.inbox.filterEscalated"),
  };

  return (
    <div style={{ padding: 28 }}>
      <div
        className="bv-dash-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "320px 1fr",
          gap: 0,
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          minHeight: 560,
        }}
      >
        {/* ── List ─────────────────────────────────────────────── */}
        <div style={{ borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 600,
                  fontSize: 16,
                  color: "var(--arctic)",
                }}
              >
                {t("dash.inbox.title")}
              </span>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--fg3)", marginTop: 2 }}>{t("dash.inbox.sub")}</div>
            <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
              {filters.map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  style={{
                    fontSize: 12,
                    fontFamily: "var(--font-sans)",
                    fontWeight: 600,
                    padding: "5px 11px",
                    borderRadius: "var(--radius-full)",
                    cursor: "pointer",
                    border: "1px solid var(--volt-border)",
                    background: filter === f ? "var(--volt)" : "var(--volt-bg)",
                    color: filter === f ? "var(--void)" : "var(--volt)",
                  }}
                >
                  {filterLabel[f]}
                </button>
              ))}
            </div>
          </div>

          <div style={{ overflowY: "auto", flex: 1 }}>
            {threads.length === 0 && (
              <div style={{ padding: 20, fontSize: 13, color: "var(--fg3)" }}>{t("dash.inbox.empty")}</div>
            )}
            {threads.map((th) => {
              const on = activeId === th.id;
              return (
                <button
                  key={th.id}
                  onClick={() => open(th.id)}
                  style={{
                    display: "flex",
                    gap: 12,
                    padding: "14px 18px",
                    width: "100%",
                    textAlign: "left",
                    cursor: "pointer",
                    border: "none",
                    borderBottom: "1px solid var(--line)",
                    alignItems: "flex-start",
                    background: on ? "var(--volt-bg)" : "transparent",
                    boxShadow: on ? "inset 2px 0 0 var(--volt)" : "none",
                  }}
                >
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: "50%",
                      background: "var(--obsidian-3)",
                      border: "1px solid var(--line-strong)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <Icon name="user" size={18} color="var(--silver)" />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span
                        style={{
                          fontSize: 14,
                          fontWeight: 600,
                          color: "var(--arctic)",
                          fontFamily: "var(--font-sans)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {th.client_name || th.client_email || "Passenger"}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--fg3)", flexShrink: 0 }}>
                        {relTime(th.last_message_at)}
                      </span>
                    </div>
                    {th.status === "escalated" && (
                      <div style={{ margin: "4px 0" }}>
                        <Pill tone="volt">{t("dash.inbox.escalated")}</Pill>
                      </div>
                    )}
                    <div
                      style={{
                        fontSize: 12.5,
                        color: on ? "var(--silver)" : "var(--fg3)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        marginTop: 3,
                      }}
                    >
                      {th.snippet}
                    </div>
                  </div>
                  {th.unread > 0 && (
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: "var(--volt)",
                        flexShrink: 0,
                        marginTop: 6,
                        boxShadow: "var(--shadow-volt-sm)",
                      }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Detail ───────────────────────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          {!detail ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--fg3)",
                fontSize: 13.5,
                padding: 20,
              }}
            >
              {t("dash.inbox.pickPrompt")}
            </div>
          ) : (
            <>
              <div
                style={{
                  padding: "14px 20px",
                  borderBottom: "1px solid var(--line)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: "50%",
                      background: "var(--obsidian-3)",
                      border: "1px solid var(--line-strong)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <Icon name="user" size={18} color="var(--silver)" />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontFamily: "var(--font-display)",
                        fontWeight: 700,
                        fontSize: 16,
                        color: "var(--arctic)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {detail.client_name || detail.client_email || "Passenger"}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--fg3)" }}>
                      {detail.status === "escalated"
                        ? t("dash.inbox.escalated")
                        : detail.status === "closed"
                          ? t("dash.inbox.closed")
                          : detail.client_email || ""}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {detail.client_email && (
                    <a href={`mailto:${detail.client_email}`} style={{ textDecoration: "none" }}>
                      <Button variant="ghost" size="sm" icon="send">
                        {t("dash.inbox.emailClient")}
                      </Button>
                    </a>
                  )}
                  {detail.status !== "closed" && (
                    <Button variant="ghost" size="sm" icon="x" onClick={doClose}>
                      {t("dash.inbox.close")}
                    </Button>
                  )}
                </div>
              </div>

              <div
                style={{
                  flex: 1,
                  overflowY: "auto",
                  padding: 20,
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                {detail.messages.map((m) => {
                  const mine = m.role !== "user";
                  return (
                    <div key={m.id} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "76%" }}>
                      {mine && (
                        <div
                          style={{
                            fontSize: 10.5,
                            color: "var(--volt)",
                            fontWeight: 600,
                            textTransform: "uppercase",
                            letterSpacing: "0.08em",
                            marginBottom: 4,
                            textAlign: "right",
                          }}
                        >
                          {m.role === "owner" ? t("dash.inbox.you") : t("dash.inbox.joules")}
                        </div>
                      )}
                      <div
                        style={{
                          padding: "10px 14px",
                          borderRadius: 12,
                          fontSize: 14,
                          lineHeight: 1.45,
                          fontFamily: "var(--font-sans)",
                          background: mine ? "var(--volt)" : "var(--obsidian-3)",
                          color: mine ? "var(--void)" : "var(--arctic)",
                          border: mine ? "none" : "1px solid var(--line-strong)",
                          borderBottomRightRadius: mine ? 4 : 12,
                          borderBottomLeftRadius: mine ? 12 : 4,
                        }}
                      >
                        {m.body}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
