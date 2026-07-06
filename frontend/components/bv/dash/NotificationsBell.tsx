"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "../Icon";
import { PushOptIn } from "../PushOptIn";
import { useI18n } from "@/lib/i18n";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
  type NotificationKind,
} from "@/lib/notifications";

const KIND_ICON: Record<NotificationKind, string> = {
  ride_new: "navigation",
  ride_cancelled: "alert-circle",
  chat_escalated: "alert-circle",
  chat_message: "message-circle",
  review_new: "star",
  discount_redeemed: "tag",
  subscription_payment_failed: "credit-card",
};

const KIND_HREF: Record<NotificationKind, string> = {
  ride_new: "/dashboard/rides",
  ride_cancelled: "/dashboard/rides",
  chat_escalated: "/dashboard/inbox",
  chat_message: "/dashboard/inbox",
  review_new: "/dashboard/reviews",
  discount_redeemed: "/dashboard/discounts",
  subscription_payment_failed: "/dashboard/settings",
};

const POLL_MS = 60_000;

export function NotificationsBell() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await listNotifications();
      setItems(res.items);
      setUnread(res.unread);
    } catch {
      /* best-effort: never surface an error for the bell */
    }
  }, []);

  // Poll on mount + every minute while the tab is visible, and immediately when
  // the tab becomes visible again (so the badge isn't up to a minute stale).
  useEffect(() => {
    refresh();
    const id = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      refresh();
    }, POLL_MS);
    const onVis = () => {
      if (!document.hidden) refresh();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refresh]);

  // Track viewport so the panel is a dropdown on desktop, a bottom sheet on mobile.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const on = () => setMobile(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const describe = useCallback(
    (n: NotificationItem): string => {
      const d = n.data || {};
      const s = (k: string) => (d[k] == null ? "" : String(d[k]));
      const name = s("client_name") || t("dash.notif.someone");
      switch (n.kind) {
        case "ride_new":
          return t("dash.notif.k.ride_new", { pickup: s("pickup") || "—", dropoff: s("dropoff") || "—" });
        case "ride_cancelled":
          return t("dash.notif.k.ride_cancelled", { pickup: s("pickup") || "—", dropoff: s("dropoff") || "—" });
        case "chat_escalated":
          return t("dash.notif.k.chat_escalated", { name });
        case "chat_message":
          return t("dash.notif.k.chat_message", { name });
        case "review_new":
          return t("dash.notif.k.review_new", { rating: s("rating") || "5" });
        case "discount_redeemed":
          return t("dash.notif.k.discount_redeemed");
        case "subscription_payment_failed":
          return t("dash.notif.k.subscription_payment_failed");
        default:
          return t("dash.notif.title");
      }
    },
    [t],
  );

  const rel = useCallback(
    (iso: string): string => {
      const then = new Date(iso).getTime();
      if (Number.isNaN(then)) return "";
      const diff = Math.round((then - Date.now()) / 1000); // negative = in the past
      const abs = Math.abs(diff);
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
      if (abs < 60) return rtf.format(Math.round(diff), "second");
      if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
      if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
      return rtf.format(Math.round(diff / 86400), "day");
    },
    [locale],
  );

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) refresh();
  };

  const onItem = (n: NotificationItem) => {
    setOpen(false);
    if (!n.read) {
      setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
      markNotificationRead(n.id).catch(() => {});
    }
    router.push(KIND_HREF[n.kind] ?? "/dashboard");
  };

  const onMarkAll = () => {
    setItems((xs) => xs.map((x) => ({ ...x, read: true })));
    setUnread(0);
    markAllNotificationsRead().catch(() => {});
  };

  const badge = unread > 9 ? "9+" : String(unread);

  const panel = (
    <div style={{ display: "flex", flexDirection: "column", maxHeight: mobile ? "70vh" : 420 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <span style={{ fontSize: 14, fontWeight: 700, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>
          {t("dash.notif.title")}
        </span>
        {items.some((n) => !n.read) && (
          <button
            onClick={onMarkAll}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--volt)",
              fontFamily: "var(--font-sans)",
              padding: 2,
            }}
          >
            {t("dash.notif.markAll")}
          </button>
        )}
      </div>
      <div style={{ overflowY: "auto", flex: 1 }}>
        {items.length === 0 ? (
          <div style={{ padding: "28px 16px", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
            {t("dash.notif.empty")}
          </div>
        ) : (
          items.map((n) => (
            <button
              key={n.id}
              onClick={() => onItem(n)}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 11,
                width: "100%",
                textAlign: "left",
                padding: "12px 16px",
                border: "none",
                borderBottom: "1px solid var(--line)",
                cursor: "pointer",
                background: n.read ? "transparent" : "var(--volt-bg)",
                fontFamily: "var(--font-sans)",
              }}
            >
              <span style={{ flexShrink: 0, marginTop: 1 }}>
                <Icon name={KIND_ICON[n.kind] ?? "bell"} size={17} color="var(--volt)" />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span
                  style={{
                    display: "block",
                    fontSize: 13,
                    fontWeight: n.read ? 500 : 600,
                    color: "var(--arctic)",
                    lineHeight: 1.4,
                  }}
                >
                  {describe(n)}
                </span>
                <span style={{ display: "block", fontSize: 11, color: "var(--fg3)", marginTop: 2 }}>
                  {rel(n.created_at)}
                </span>
              </span>
              {!n.read && (
                <span
                  style={{
                    flexShrink: 0,
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "var(--volt)",
                    marginTop: 4,
                  }}
                />
              )}
            </button>
          ))
        )}
      </div>
      <PushOptIn compact />
    </div>
  );

  return (
    <div ref={wrapRef} style={{ position: "relative", display: "flex" }}>
      <button
        onClick={toggle}
        aria-label={t("dash.notif.title")}
        aria-expanded={open}
        style={{
          position: "relative",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 2,
          display: "flex",
          alignItems: "center",
        }}
      >
        <Icon name="bell" size={19} color={open ? "var(--arctic)" : "var(--silver)"} />
        {unread > 0 && (
          <span
            style={{
              position: "absolute",
              top: -5,
              right: -6,
              minWidth: 16,
              height: 16,
              padding: "0 4px",
              borderRadius: 8,
              background: "var(--volt)",
              color: "var(--void)",
              fontSize: 10,
              fontWeight: 700,
              lineHeight: "16px",
              textAlign: "center",
              boxShadow: "var(--shadow-volt-sm)",
              fontFamily: "var(--font-sans)",
            }}
          >
            {badge}
          </span>
        )}
      </button>

      {open &&
        (mobile ? (
          <div
            onClick={() => setOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 70,
              background: "rgba(5,5,9,0.6)",
              backdropFilter: "blur(3px)",
              display: "flex",
              alignItems: "flex-end",
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                width: "100%",
                background: "var(--obsidian)",
                borderTop: "1px solid var(--volt-border)",
                borderTopLeftRadius: 18,
                borderTopRightRadius: 18,
                paddingBottom: "env(safe-area-inset-bottom)",
                boxShadow: "var(--shadow-pop)",
                overflow: "hidden",
              }}
            >
              <div style={{ width: 38, height: 4, borderRadius: 99, background: "var(--line-strong)", margin: "10px auto 2px" }} />
              {panel}
            </div>
          </div>
        ) : (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 10px)",
              right: 0,
              zIndex: 50,
              width: 340,
              maxWidth: "calc(100vw - 32px)",
              background: "var(--obsidian)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-pop)",
              overflow: "hidden",
            }}
          >
            {panel}
          </div>
        ))}
    </div>
  );
}
