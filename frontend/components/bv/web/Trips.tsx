"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { RideChatPanel } from "../RideChat";
import { Card } from "../ui";
import { useI18n } from "@/lib/i18n";
import { cancelRide, listRides, type RideRow } from "@/lib/booking";

// Statuses that count as a real, upcoming trip vs a finished one. QUOTED/REQUESTED
// are unpaid drafts — they are not shown on /trips.
const ACTIVE = ["confirmed", "assigned", "en_route"];
const PAST = ["completed", "cancelled", "no_show"];

function ActionBtn({
  icon,
  label,
  onClick,
  disabled,
  badge,
}: {
  icon: string;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        position: "relative",
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        padding: "10px 12px",
        background: "var(--obsidian-3)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-md)",
        color: disabled ? "var(--fg3)" : "var(--arctic)",
        fontFamily: "var(--font-sans)",
        fontSize: 13.5,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        transition: "all .15s ease-out",
      }}
    >
      <Icon name={icon} size={18} color={disabled ? "var(--fg3)" : "var(--volt)"} />
      {label}
      {!!badge && badge > 0 && (
        <span
          style={{
            position: "absolute",
            top: 4,
            right: 8,
            minWidth: 18,
            height: 18,
            padding: "0 5px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--volt)",
            color: "var(--void)",
            borderRadius: "var(--radius-full)",
            fontSize: 11,
            fontWeight: 700,
          }}
        >
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );
}

function StatusBadge({ status, label }: { status: string; label: string }) {
  const active = ACTIVE.includes(status);
  const danger = status === "cancelled" || status === "no_show";
  const color = danger ? "var(--danger)" : active ? "var(--volt)" : "var(--silver)";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color,
        fontFamily: "var(--font-display)",
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
      {label}
    </span>
  );
}

function telHref(phone: string) {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

function fmtWhen(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(lang === "es" ? "es-US" : "en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

function money(r: RideRow): string {
  const v = Math.round(r.fare_total ?? 0);
  return `$${v}`;
}

function UpcomingCard({
  ride,
  t,
  lang,
  onCancel,
  cancelling,
  onMessage,
}: {
  ride: RideRow;
  t: (k: string) => string;
  lang: string;
  onCancel: () => void;
  cancelling: boolean;
  onMessage: () => void;
}) {
  const driver = ride.assigned_driver;
  const phone = driver?.phone || null;
  return (
    <Card glow pad={20}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <StatusBadge status={ride.status} label={t(`trips.st.${ride.status}`)} />
          <span style={{ fontSize: 13, color: "var(--silver)" }}>{fmtWhen(ride.scheduled_at, lang)}</span>
        </div>

        {/* Route */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--silver)" }}>
            <Icon name="circle-dot" size={16} color="var(--volt)" /> {ride.pickup}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--silver)" }}>
            <Icon name="map-pin" size={16} color="var(--volt)" /> {ride.dropoff}
          </div>
        </div>

        {/* Stats */}
        <div style={{ display: "flex", gap: 16, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--fg3)", marginBottom: 4 }}>{t("trips.fare")}</div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--volt)" }}>
              {money(ride)}
            </div>
          </div>
          {ride.flight_number && (
            <div>
              <div style={{ fontSize: 11, color: "var(--fg3)", marginBottom: 4 }}>{t("trips.flight")}</div>
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--arctic)" }}>
                {ride.flight_number}
              </div>
            </div>
          )}
        </div>

        {/* Driver + contact */}
        <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          {driver ? (
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: "50%",
                  background: "var(--volt-bg)",
                  border: "1px solid var(--volt-border)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Icon name="user" size={18} color="var(--volt)" />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)" }}>
                  {driver.name || t("trips.driver")}
                </div>
                <div style={{ fontSize: 12, color: "var(--fg3)" }}>
                  {[driver.vehicle, driver.rating ? `★ ${driver.rating.toFixed(2)}` : null]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: "var(--fg3)", marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name="clock" size={15} color="var(--fg3)" /> {t("trips.driverPending")}
            </div>
          )}
          <div style={{ display: "flex", gap: 10 }}>
            <ActionBtn
              icon="phone"
              label={t("trips.call")}
              disabled={!phone}
              onClick={phone ? () => { window.location.href = telHref(phone); } : undefined}
            />
            <ActionBtn
              icon="message-circle"
              label={t("trips.message")}
              disabled={!ride.chat_open}
              badge={ride.unread_messages}
              onClick={ride.chat_open ? onMessage : undefined}
            />
          </div>
        </div>

        {(ride.status === "confirmed" || ride.status === "assigned") && (
          <button
            onClick={onCancel}
            disabled={cancelling}
            style={{
              width: "100%",
              padding: "11px 12px",
              background: "transparent",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-md)",
              color: "var(--danger)",
              fontFamily: "var(--font-sans)",
              fontSize: 13.5,
              fontWeight: 600,
              cursor: cancelling ? "not-allowed" : "pointer",
              opacity: cancelling ? 0.6 : 1,
              transition: "all .15s ease-out",
            }}
          >
            {cancelling ? t("trips.cancelling") : t("trips.cancel")}
          </button>
        )}
      </div>
    </Card>
  );
}

function PastRow({ ride, t, lang }: { ride: RideRow; t: (k: string) => string; lang: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 0",
        borderBottom: "1px solid var(--line)",
        gap: 12,
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <StatusBadge status={ride.status} label={t(`trips.st.${ride.status}`)} />
          <span style={{ fontSize: 12, color: "var(--fg3)" }}>{fmtWhen(ride.scheduled_at, lang)}</span>
        </div>
        <div
          style={{
            fontSize: 13.5,
            color: "var(--silver)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {ride.pickup} → {ride.dropoff}
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: "var(--arctic)" }}>
          {money(ride)}
        </div>
        {ride.status === "completed" && (
          <a
            href={`/review?ride=${ride.id}`}
            style={{ fontSize: 12.5, fontWeight: 600, color: "var(--volt)", textDecoration: "none", whiteSpace: "nowrap" }}
          >
            ★ {t("trips.leaveReview")}
          </a>
        )}
      </div>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 16px", color: "var(--fg3)", fontSize: 14 }}>{children}</div>
  );
}

export function Trips() {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const [rides, setRides] = useState<RideRow[] | null>(null);
  const [error, setError] = useState(false);
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [chatRide, setChatRide] = useState<number | null>(null);

  const load = useCallback(() => {
    setError(false);
    return listRides()
      .then((rows) => setRides(rows))
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    setRides(null);
    load();
  }, [load]);

  // Deep-link from a push / the bell: `/trips?chat=<ride_id>` opens that ride's
  // chat once the trips have loaded. Applied once, then the URL is cleaned so a
  // refresh or back-navigation doesn't reopen it.
  const chatParamApplied = useRef(false);
  useEffect(() => {
    if (chatParamApplied.current || !rides) return;
    const c = new URLSearchParams(window.location.search).get("chat");
    if (c) {
      const id = Number(c);
      if (rides.some((r) => r.id === id)) setChatRide(id);
      window.history.replaceState(null, "", "/trips");
    }
    chatParamApplied.current = true;
  }, [rides]);

  const handleCancel = async (ride: RideRow) => {
    const within24h =
      !!ride.scheduled_at &&
      new Date(ride.scheduled_at).getTime() - Date.now() < 24 * 3600 * 1000;
    const msg = within24h ? t("trips.cancel.warn24h") : t("trips.cancel.confirm");
    if (typeof window !== "undefined" && !window.confirm(msg)) return;
    setCancellingId(ride.id);
    try {
      await cancelRide(ride.id);
      await load();
    } catch {
      setError(true);
    } finally {
      setCancellingId(null);
    }
  };

  const upcoming = (rides ?? [])
    .filter((r) => ACTIVE.includes(r.status))
    .sort((a, b) => (a.scheduled_at || "").localeCompare(b.scheduled_at || ""));
  const past = (rides ?? [])
    .filter((r) => PAST.includes(r.status))
    .sort((a, b) => (b.scheduled_at || "").localeCompare(a.scheduled_at || ""));
  const list = tab === "upcoming" ? upcoming : past;

  return (
    <div style={{ maxWidth: 480, margin: "0 auto", padding: "32px 0" }}>
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 28,
          color: "var(--arctic)",
          margin: "0 0 18px",
        }}
      >
        {t("trips.title")}
      </h2>

      {/* Tabs */}
      <div
        role="tablist"
        style={{
          display: "flex",
          gap: 6,
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: 4,
          marginBottom: 18,
        }}
      >
        {(["upcoming", "past"] as const).map((key) => {
          const active = tab === key;
          const count = key === "upcoming" ? upcoming.length : past.length;
          return (
            <button
              key={key}
              role="tab"
              aria-selected={active}
              onClick={() => setTab(key)}
              style={{
                flex: 1,
                cursor: "pointer",
                border: "none",
                borderRadius: "var(--radius-sm)",
                padding: "9px 8px",
                fontFamily: "var(--font-sans)",
                fontSize: 13.5,
                fontWeight: 600,
                color: active ? "var(--obsidian)" : "var(--silver)",
                background: active ? "var(--volt)" : "transparent",
                transition: "all .15s ease-out",
              }}
            >
              {t(key === "upcoming" ? "trips.upcoming" : "trips.past")}
              {rides && count > 0 ? ` (${count})` : ""}
            </button>
          );
        })}
      </div>

      {error ? (
        <Muted>{t("trips.error")}</Muted>
      ) : rides === null ? (
        <Muted>{t("trips.loading")}</Muted>
      ) : list.length === 0 ? (
        <Muted>{tab === "upcoming" ? t("trips.empty") : t("trips.emptyPast")}</Muted>
      ) : tab === "upcoming" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {list.map((r) => (
            <UpcomingCard
              key={r.id}
              ride={r}
              t={t}
              lang={lang}
              onCancel={() => handleCancel(r)}
              cancelling={cancellingId === r.id}
              onMessage={() => setChatRide(r.id)}
            />
          ))}
        </div>
      ) : (
        <Card pad={4}>
          <div style={{ padding: "0 16px" }}>
            {list.map((r) => (
              <PastRow key={r.id} ride={r} t={t} lang={lang} />
            ))}
          </div>
        </Card>
      )}

      {chatRide != null && (
        <RideChatPanel
          rideId={chatRide}
          viewer="client"
          onClose={() => {
            setChatRide(null);
            void load();
          }}
        />
      )}
    </div>
  );
}
