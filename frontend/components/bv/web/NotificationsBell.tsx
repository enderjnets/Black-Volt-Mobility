"use client";

/* Passenger notifications bell (the client side of the per-ride messaging).
   Mirrors the driver dashboard bell but is keyed to the signed-in passenger and
   routes to their trips: a `ride_message` opens that ride's chat directly
   (`/trips?chat=<id>`), refunds land on `/trips`. Mounted in the web header only
   when a passenger is authenticated. Polls every minute while visible. */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import {
  listClientNotifications,
  markAllClientNotificationsRead,
  markClientNotificationRead,
  type ClientNotificationItem,
  type ClientNotificationKind,
} from "@/lib/clientNotifications";
import { Icon } from "../Icon";
import { PushOptIn } from "../PushOptIn";

const KIND_ICON: Record<ClientNotificationKind, string> = {
  ride_message: "message-circle",
  refund_full: "credit-card",
  refund_partial: "credit-card",
};

const POLL_MS = 60_000;

export function ClientNotificationsBell() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [items, setItems] = useState<ClientNotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await listClientNotifications();
      setItems(res.items);
      setUnread(res.unread);
    } catch {
      /* best-effort: never surface an error for the bell */
    }
  }, []);

  // Poll on mount + every minute while visible, and immediately on re-focus.
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

  // Dropdown on desktop, bottom sheet on mobile.
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
    (n: ClientNotificationItem): string => {
      switch (n.kind) {
        case "ride_message":
          return t("client.notif.k.ride_message");
        case "refund_full":
          return t("client.notif.k.refund_full");
        case "refund_partial":
          return t("client.notif.k.refund_partial");
        default:
          return t("client.notif.title");
      }
    },
    [t],
  );

  const rel = useCallback(
    (iso: string): string => {
      const then = new Date(iso).getTime();
      if (Number.isNaN(then)) return "";
      const diff = Math.round((then - Date.now()) / 1000); // negative = past
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

  const onItem = (n: ClientNotificationItem) => {
    setOpen(false);
    if (!n.read) {
      setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
      markClientNotificationRead(n.id).catch(() => {});
    }
    const rideId = (n.data as { ride_id?: number } | undefined)?.ride_id;
    router.push(n.kind === "ride_message" && rideId ? `/trips?chat=${rideId}` : "/trips");
  };

  const onMarkAll = () => {
    setItems((xs) => xs.map((x) => ({ ...x, read: true })));
    setUnread(0);
    markAllClientNotificationsRead().catch(() => {});
  };

  const badge = unread > 9 ? "9+" : String(unread);

  const panel = (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 14,
            color: "var(--arctic)",
          }}
        >
          {t("client.notif.title")}
        </span>
        {items.length > 0 && (
          <button
            onClick={onMarkAll}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--volt)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
            }}
          >
            {t("client.notif.markAll")}
          </button>
        )}
      </div>
      {/* A definite min/max height so the list never collapses to 0 inside the
          content-sized mobile sheet (a flex:1 scroll child would). */}
      <div
        style={{
          overflowY: "auto",
          minHeight: mobile ? 220 : 140,
          maxHeight: mobile ? "60vh" : 320,
        }}
      >
        {items.length === 0 ? (
          <div
            style={{ padding: "28px 16px", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}
          >
            {t("client.notif.empty")}
          </div>
        ) : (
          items.map((n) => (
            <button
              key={n.id}
              onClick={() => onItem(n)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: "11px 16px",
                background: n.read ? "transparent" : "var(--volt-bg)",
                border: "none",
                borderBottom: "1px solid var(--line)",
                textAlign: "left",
                cursor: "pointer",
              }}
            >
              <span style={{ flexShrink: 0, marginTop: 2 }}>
                <Icon name={KIND_ICON[n.kind] ?? "bell"} size={16} color="var(--volt)" />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span
                  style={{ display: "block", fontSize: 13, color: "var(--arctic)", lineHeight: 1.4 }}
                >
                  {describe(n)}
                </span>
                <span
                  style={{ display: "block", fontSize: 11, color: "var(--fg3)", marginTop: 2 }}
                >
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
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button
        onClick={toggle}
        aria-label={t("client.notif.title")}
        style={{
          position: "relative",
          width: 38,
          height: 38,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "transparent",
          border: "none",
          cursor: "pointer",
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
              borderRadius: 99,
              background: "var(--volt)",
              color: "var(--void)",
              fontSize: 10,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
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
                borderTop: "1px solid var(--line-strong)",
                borderTopLeftRadius: 18,
                borderTopRightRadius: 18,
                paddingBottom: "env(safe-area-inset-bottom)",
                boxShadow: "var(--shadow-pop)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: 38,
                  height: 4,
                  borderRadius: 99,
                  background: "var(--line-strong)",
                  margin: "10px auto 2px",
                }}
              />
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
