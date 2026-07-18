"use client";

/* Per-ride passenger<->driver chat. `RideChatThread` is the message list +
   composer (polls every 6s while mounted and the tab is visible); `RideChatPanel`
   wraps it in a mobile-first bottom sheet for the client's /trips view. The driver
   embeds the thread directly inside the ride drawer. `viewer` decides which side
   is "mine" (right, volt) vs the other party (left, obsidian). */
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "./Icon";
import { useI18n } from "@/lib/i18n";
import {
  listRideMessages,
  sendRideMessage,
  type RideMessage,
} from "@/lib/rideMessages";

const POLL_MS = 6000;

export function RideChatThread({
  rideId,
  viewer,
  onActivity,
  height = 340,
}: {
  rideId: number;
  viewer: "client" | "driver";
  onActivity?: () => void;
  height?: number;
}) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<RideMessage[]>([]);
  const [chatOpen, setChatOpen] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const lastId = useRef(0);
  const scroller = useRef<HTMLDivElement>(null);
  // Keep the parent callback in a ref so `refresh`/`send` stay stable across
  // renders even if the parent passes a fresh function each time — otherwise the
  // polling effect would tear down and re-run (re-fetching) on every render.
  const onActivityRef = useRef(onActivity);
  useEffect(() => {
    onActivityRef.current = onActivity;
  }, [onActivity]);

  const refresh = useCallback(
    async (incremental: boolean) => {
      try {
        const res = await listRideMessages(rideId, incremental ? lastId.current : undefined);
        setChatOpen(res.chat_open);
        if (res.messages.length) {
          setMessages((prev) => {
            const seen = new Set(prev.map((m) => m.id));
            const merged = incremental
              ? [...prev, ...res.messages.filter((m) => !seen.has(m.id))]
              : res.messages;
            lastId.current = merged.reduce((mx, m) => Math.max(mx, m.id), 0);
            return merged;
          });
        } else if (!incremental) {
          setMessages([]);
          lastId.current = 0;
        }
        // Notify the parent (to refresh unread badges) on the opening load and
        // whenever new messages actually arrived — never on empty polls.
        if (!incremental || res.messages.length) onActivityRef.current?.();
      } catch {
        // transient; the next poll retries
      }
    },
    [rideId],
  );

  useEffect(() => {
    void refresh(false);
    const tick = () => {
      if (!document.hidden) void refresh(true);
    };
    const id = window.setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [refresh]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    setErr(null);
    try {
      const msg = await sendRideMessage(rideId, text);
      setInput("");
      setMessages((prev) => {
        const next = prev.some((m) => m.id === msg.id) ? prev : [...prev, msg];
        lastId.current = Math.max(lastId.current, msg.id);
        return next;
      });
      onActivityRef.current?.();
    } catch (e) {
      setErr(e instanceof Error && e.message === "chat_closed" ? t("ride.chat.closed") : t("ride.chat.error"));
      if (e instanceof Error && e.message === "chat_closed") setChatOpen(false);
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        ref={scroller}
        style={{
          height,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: "4px 2px",
        }}
      >
        {messages.length === 0 ? (
          <div style={{ margin: "auto", fontSize: 13, color: "var(--fg3)", textAlign: "center" }}>
            {t("ride.chat.empty")}
          </div>
        ) : (
          messages.map((m) => {
            const mine = m.sender === viewer;
            return (
              <div
                key={m.id}
                style={{
                  alignSelf: mine ? "flex-end" : "flex-start",
                  maxWidth: "82%",
                  padding: "8px 12px",
                  fontSize: 13.5,
                  lineHeight: 1.45,
                  borderRadius: mine ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
                  background: mine ? "var(--volt)" : "var(--obsidian-3)",
                  color: mine ? "var(--void)" : "var(--arctic)",
                  border: mine ? "none" : "1px solid var(--line-strong)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {m.body}
              </div>
            );
          })
        )}
      </div>

      {chatOpen ? (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={t("ride.chat.placeholder")}
            maxLength={2000}
            aria-label={t("ride.chat.placeholder")}
            style={{
              flex: 1,
              padding: "10px 12px",
              background: "var(--obsidian-3)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-md)",
              color: "var(--arctic)",
              fontFamily: "var(--font-sans)",
              fontSize: 14,
              outline: "none",
            }}
          />
          <button
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            aria-label={t("ride.chat.send")}
            style={{
              width: 42,
              height: 42,
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--volt)",
              border: "none",
              borderRadius: "var(--radius-md)",
              color: "var(--void)",
              cursor: sending || !input.trim() ? "not-allowed" : "pointer",
              opacity: sending || !input.trim() ? 0.5 : 1,
            }}
          >
            <Icon name="send" size={18} color="var(--void)" />
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 12.5, color: "var(--fg3)", textAlign: "center", padding: "6px 0" }}>
          {t("ride.chat.closed")}
        </div>
      )}
      {err && (
        <div style={{ fontSize: 12, color: "var(--danger)", textAlign: "center" }}>{err}</div>
      )}
    </div>
  );
}

export function RideChatPanel({
  rideId,
  viewer,
  title,
  onClose,
  onActivity,
}: {
  rideId: number;
  viewer: "client" | "driver";
  title?: string;
  onClose: () => void;
  onActivity?: () => void;
}) {
  const { t } = useI18n();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        background: "rgba(0,0,0,.6)",
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 520,
          maxHeight: "85dvh",
          background: "var(--void)",
          border: "1px solid var(--line-strong)",
          borderRadius: "18px 18px 0 0",
          padding: "16px 16px calc(16px + env(safe-area-inset-bottom))",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          boxShadow: "var(--shadow-pop)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="message-circle" size={18} color="var(--volt)" />
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--arctic)" }}>
              {title || t("ride.chat.title")}
            </span>
          </div>
          <button
            onClick={onClose}
            aria-label={t("ride.chat.close")}
            style={{
              width: 32,
              height: 32,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "transparent",
              border: "none",
              color: "var(--fg3)",
              cursor: "pointer",
            }}
          >
            <Icon name="x" size={20} color="var(--fg3)" />
          </button>
        </div>
        <RideChatThread rideId={rideId} viewer={viewer} onActivity={onActivity} height={360} />
      </div>
    </div>
  );
}
