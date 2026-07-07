"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";
import { ApiError } from "@/lib/booking";
import { type ChatApiMsg, getChat, sendChatMessage } from "@/lib/chat";
import { useWeb } from "./WebShell";

type Msg = { role: "user" | "ai"; text: string };

const NUDGE_KEYS = ["chat.nudge1", "chat.nudge2", "chat.nudge3"] as const;

function toBubbles(api: ChatApiMsg[]): Msg[] {
  return api.map((m) => ({ role: m.role === "user" ? "user" : "ai", text: m.body }));
}

export function ChatAssistant({ open, setOpen }: { open: boolean; setOpen: (v: boolean) => void }) {
  const { t, lang } = useI18n();
  const { user, openSignIn } = useWeb();
  const [msgs, setMsgs] = useState<Msg[]>([{ role: "ai", text: t("chat.greet") }]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const pendingRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [nudging, setNudging] = useState(false);
  const [nudgeIdx, setNudgeIdx] = useState(0);
  const [wiggle, setWiggle] = useState(false);

  const dismissNudge = () => {
    setNudging(false);
    try {
      sessionStorage.setItem("bv_joules_seen", "1");
    } catch {
      /* private mode: just won't persist across reloads */
    }
  };

  // Proactive nudge: a beat after load, the launcher wiggles and floats a rotating
  // one-liner so first-time visitors notice Joules. Stops for the session on the
  // first interaction (open or dismiss). Motion is neutralized under reduced-motion
  // by the global rule in globals.css.
  useEffect(() => {
    if (open || typeof window === "undefined") return;
    try {
      if (sessionStorage.getItem("bv_joules_seen")) return;
    } catch {
      /* ignore storage access errors */
    }
    let cycle: ReturnType<typeof setInterval> | undefined;
    let wig: ReturnType<typeof setTimeout> | undefined;
    const kick = () => {
      setWiggle(true);
      wig = setTimeout(() => setWiggle(false), 700);
    };
    const start = setTimeout(() => {
      setNudging(true);
      kick();
      cycle = setInterval(() => {
        setNudgeIdx((i) => (i + 1) % NUDGE_KEYS.length);
        kick();
      }, 20000);
    }, 7000);
    return () => {
      clearTimeout(start);
      if (wig) clearTimeout(wig);
      if (cycle) clearInterval(cycle);
    };
  }, [open]);

  // Load the persisted history once a signed-in passenger opens the panel.
  useEffect(() => {
    if (!open || !user || loaded) return;
    setLoaded(true);
    getChat()
      .then((h) => {
        const bubbles = toBubbles(h.messages);
        if (bubbles.length) setMsgs(bubbles);
      })
      .catch(() => {});
  }, [open, user, loaded]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [msgs, open, typing]);

  // Keep the initial greeting in sync with the page language until real history
  // loads. The i18n provider hydrates `lang` from localStorage after mount, so the
  // greeting captured at first render (English default) must follow the switch.
  useEffect(() => {
    setMsgs((m) =>
      m.length === 1 && m[0].role === "ai" ? [{ role: "ai", text: t("chat.greet") }] : m,
    );
  }, [lang, t]);

  async function deliver(text: string, base?: Msg[]) {
    setTyping(true);
    try {
      const res = await sendChatMessage(text, lang);
      setMsgs((m) => [...(base ?? m), { role: "ai", text: res.reply }]);
    } catch (e) {
      const key = e instanceof ApiError && e.status === 429 ? "chat.rateLimited" : "chat.error";
      setMsgs((m) => [...(base ?? m), { role: "ai", text: t(key) }]);
    } finally {
      setTyping(false);
    }
  }

  const send = async (text?: string) => {
    const v = (text ?? input).trim();
    if (!v || typing) return;
    setInput("");

    // Gate: an anonymous visitor must sign in with Google before Joules replies.
    if (!user) {
      pendingRef.current = v;
      setMsgs((m) => [...m, { role: "user", text: v }]);
      openSignIn(async () => {
        const pending = pendingRef.current;
        pendingRef.current = null;
        if (!pending) return;
        // Rebuild from any server history (returning user) + this message, then send.
        let base: Msg[] = [];
        try {
          const h = await getChat();
          base = toBubbles(h.messages);
        } catch {
          base = [{ role: "ai", text: t("chat.greet") }];
        }
        setLoaded(true);
        const withPending: Msg[] = [...base, { role: "user", text: pending }];
        setMsgs(withPending);
        await deliver(pending, withPending);
      });
      return;
    }

    const next: Msg[] = [...msgs, { role: "user", text: v }];
    setMsgs(next);
    await deliver(v, next);
  };

  return (
    <>
      {nudging && !open && (
        <div
          className="bv-chat-nudge"
          role="button"
          tabIndex={0}
          onClick={() => {
            dismissNudge();
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              dismissNudge();
              setOpen(true);
            }
          }}
        >
          <span
            style={{
              fontSize: 13.5,
              fontFamily: "var(--font-sans)",
              color: "var(--arctic)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {t(NUDGE_KEYS[nudgeIdx])}
          </span>
          <button
            aria-label={lang === "es" ? "Descartar" : "Dismiss"}
            onClick={(e) => {
              e.stopPropagation();
              dismissNudge();
            }}
            style={{
              width: 24,
              height: 24,
              flexShrink: 0,
              borderRadius: "50%",
              border: "none",
              background: "transparent",
              color: "var(--fg3)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 0,
            }}
          >
            <Icon name="x" size={13} color="currentColor" />
          </button>
        </div>
      )}
      <button
        onClick={() => {
          dismissNudge();
          setOpen(!open);
        }}
        aria-label="Assistant"
        className={`bv-chat-launcher${nudging && !open ? " bv-nudging" : ""}${
          wiggle && !open ? " bv-wiggle" : ""
        }`}
        style={{
          position: "fixed",
          right: 24,
          bottom: 24,
          zIndex: 46,
          width: 56,
          height: 56,
          borderRadius: "50%",
          border: "1px solid var(--volt-border)",
          background: "var(--volt)",
          color: "var(--void)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "var(--shadow-volt)",
          transition: "transform .16s ease-out",
          transform: open ? "scale(0.9)" : "scale(1)",
        }}
      >
        <Icon name={open ? "x" : "sparkles"} size={24} color="var(--void)" fill={open ? "none" : "var(--void)"} />
        {nudging && !open && (
          <span
            aria-hidden
            style={{
              position: "absolute",
              top: 9,
              right: 9,
              width: 11,
              height: 11,
              borderRadius: "50%",
              background: "var(--void)",
              border: "2px solid var(--volt)",
              boxShadow: "0 0 0 2px var(--volt)",
            }}
          />
        )}
      </button>

      {open && (
        <div
          className="bv-chat-panel"
          style={{
            position: "fixed",
            right: 24,
            bottom: 92,
            zIndex: 46,
            width: 360,
            maxWidth: "calc(100vw - 48px)",
            height: 480,
            maxHeight: "calc(100dvh - 140px)",
            display: "flex",
            flexDirection: "column",
            background: "var(--obsidian)",
            border: "1px solid var(--volt-border)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-pop), var(--shadow-volt-sm)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 11,
              padding: "14px 16px",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: "50%",
                background: "var(--volt-bg)",
                border: "1px solid var(--volt-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon name="sparkles" size={17} color="var(--volt)" />
            </div>
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 600,
                  fontSize: 15,
                  color: "var(--arctic)",
                }}
              >
                {t("chat.title")}
              </div>
              <div style={{ fontSize: 11, color: "var(--fg3)" }}>{t("chat.sub")}</div>
            </div>
          </div>

          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {msgs.map((m, i) => (
              <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "82%" }}>
                <div
                  style={{
                    padding: "10px 13px",
                    borderRadius: 12,
                    fontSize: 13.5,
                    lineHeight: 1.45,
                    fontFamily: "var(--font-sans)",
                    background: m.role === "user" ? "var(--volt)" : "var(--obsidian-3)",
                    color: m.role === "user" ? "var(--void)" : "var(--arctic)",
                    borderBottomRightRadius: m.role === "user" ? 4 : 12,
                    borderBottomLeftRadius: m.role === "user" ? 12 : 4,
                    border: m.role === "user" ? "none" : "1px solid var(--line-strong)",
                  }}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {typing && (
              <div style={{ alignSelf: "flex-start", maxWidth: "82%" }}>
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    borderBottomLeftRadius: 4,
                    background: "var(--obsidian-3)",
                    border: "1px solid var(--line-strong)",
                    display: "flex",
                    gap: 4,
                  }}
                >
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: "var(--volt)",
                        animation: `bvBlink 1s ${i * 0.18}s infinite ease-in-out`,
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          {msgs.length <= 1 && !typing && (
            <div style={{ display: "flex", gap: 7, padding: "0 16px 10px", flexWrap: "wrap" }}>
              {["chat.q1", "chat.q2", "chat.q3"].map((k) => (
                <button
                  key={k}
                  onClick={() => send(t(k))}
                  style={{
                    fontSize: 12,
                    fontFamily: "var(--font-sans)",
                    color: "var(--volt)",
                    background: "var(--volt-bg)",
                    border: "1px solid var(--volt-border)",
                    borderRadius: "var(--radius-full)",
                    padding: "6px 11px",
                    cursor: "pointer",
                  }}
                >
                  {t(k)}
                </button>
              ))}
            </div>
          )}

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "12px 14px",
              borderTop: "1px solid var(--line)",
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("chat.ph")}
              onKeyDown={(e) => e.key === "Enter" && send()}
              style={{
                flex: 1,
                background: "var(--obsidian-3)",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--radius-full)",
                padding: "10px 14px",
                color: "var(--arctic)",
                fontSize: 13.5,
                fontFamily: "var(--font-sans)",
                outline: "none",
              }}
            />
            <button
              onClick={() => send()}
              aria-label="Send"
              style={{
                width: 38,
                height: 38,
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
      )}
    </>
  );
}
