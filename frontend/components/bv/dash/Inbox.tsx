"use client";

import { useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { bvComplete } from "@/lib/bvAI";
import { BV_THREADS, CHANNEL, type Thread } from "./data";

export function Inbox() {
  const { t } = useI18n();
  const [active, setActive] = useState<Thread>(BV_THREADS[0]);
  const [draft, setDraft] = useState("");
  const [drafting, setDrafting] = useState(false);

  const aiReply = async () => {
    if (drafting) return;
    setDrafting(true);
    const transcript = active.msgs.map((m) => ({ role: (m.from === "client" ? "user" : "ai") as "user" | "ai", text: m.text }));
    const reply = await bvComplete(transcript, { mock: () => "Happy to help — Ender's black EV9 will be ready. Anything else?" });
    setDraft(reply);
    setDrafting(false);
  };

  const ch = CHANNEL[active.channel];

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
          height: 560,
        }}
      >
        <div style={{ borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--arctic)" }}>{t("dash.inbox.title")}</span>
            <Pill tone="volt">{t("dash.inbox.new")}</Pill>
          </div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {BV_THREADS.map((th) => {
              const c = CHANNEL[th.channel];
              const on = active.id === th.id;
              return (
                <button
                  key={th.id}
                  onClick={() => {
                    setActive(th);
                    setDraft("");
                  }}
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
                      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", whiteSpace: "nowrap" }}>{th.client}</span>
                      <span style={{ fontSize: 11, color: "var(--fg3)", flexShrink: 0 }}>{th.time}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, margin: "3px 0 4px" }}>
                      <Icon name={c.icon} size={12} color={c.color} fill={th.channel === "chat" ? c.color : "none"} />
                      <span style={{ fontSize: 10.5, fontWeight: 600, color: c.color, textTransform: "uppercase", letterSpacing: "0.06em" }}>{t(c.labelKey)}</span>
                    </div>
                    <div style={{ fontSize: 12.5, color: on ? "var(--silver)" : "var(--fg3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {th.snippet}
                    </div>
                  </div>
                  {th.unread && (
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--volt)", flexShrink: 0, marginTop: 6, boxShadow: "var(--shadow-volt-sm)" }} />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
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
                }}
              >
                <Icon name="user" size={18} color="var(--silver)" />
              </div>
              <div>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--arctic)", whiteSpace: "nowrap" }}>{active.client}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: ch.color }}>
                  <Icon name={ch.icon} size={12} color={ch.color} fill={active.channel === "chat" ? ch.color : "none"} />
                  {t(ch.labelKey)}
                </div>
              </div>
            </div>
            <Button variant="ghost" size="sm" icon="phone">
              {t("dash.inbox.call")}
            </Button>
          </div>

          {active.channel === "call" && (
            <div style={{ margin: "14px 20px 0", padding: 14, borderRadius: "var(--radius-md)", background: "rgba(43,212,160,0.08)", border: "1px solid rgba(43,212,160,0.35)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <Icon name="sparkles" size={15} color="var(--success)" />
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--success)", textTransform: "uppercase", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>
                  {t("dash.inbox.handled", { d: active.duration ?? "" })}
                </span>
              </div>
              <div style={{ fontSize: 13, color: "var(--silver)", lineHeight: 1.5 }}>{active.summary}</div>
            </div>
          )}

          <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
            {active.msgs.map((m, i) => {
              const mine = m.from !== "client";
              return (
                <div key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: "76%" }}>
                  {m.ai && (
                    <div style={{ fontSize: 10.5, color: "var(--volt)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4, textAlign: "right" }}>
                      {t("dash.ai")}
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
                    {m.text}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 18px", borderTop: "1px solid var(--line)" }}>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("dash.inbox.composer")}
              style={{
                flex: 1,
                minWidth: 0,
                background: "var(--obsidian-3)",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--radius-full)",
                padding: "11px 16px",
                color: "var(--arctic)",
                fontSize: 14,
                fontFamily: "var(--font-sans)",
                outline: "none",
              }}
            />
            <Button variant="plain" size="sm" icon="sparkles" onClick={aiReply}>
              {drafting ? t("dash.inbox.drafting") : t("dash.inbox.aiReply")}
            </Button>
            <button
              onClick={() => setDraft("")}
              aria-label="Send"
              style={{
                width: 40,
                height: 40,
                flexShrink: 0,
                borderRadius: "50%",
                border: "none",
                cursor: "pointer",
                background: "var(--volt)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "var(--shadow-volt-sm)",
              }}
            >
              <Icon name="send" size={17} color="var(--void)" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
