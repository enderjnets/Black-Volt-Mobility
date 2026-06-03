"use client";

/* Ride detail drawer for the driver: full trip + client + payment, with status
   actions (en route / complete / cancel / no-show) and Square capture. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { useI18n } from "@/lib/i18n";
import { getRideDetail, type PaymentMethod, type RideDetail as RD, updateRide } from "@/lib/booking";
import { capturePayment } from "@/lib/payments";
import { StatusPill } from "./DashShell";
import { fmtWhen, uiStatus } from "./status";

const METHODS: PaymentMethod[] = ["cash", "square", "venmo", "zelle", "other"];

function Row({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5, color: "var(--silver)", minWidth: 0 }}>
      <Icon name={icon} size={15} color="var(--volt)" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{children}</span>
    </div>
  );
}

export function RideDetail({
  rideId,
  onClose,
  onChanged,
}: {
  rideId: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const [ride, setRide] = useState<RD | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => getRideDetail(rideId).then(setRide).catch(() => setErr("load"));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rideId]);

  const patch = async (body: { status?: string; payment_method?: PaymentMethod; paid?: boolean }) => {
    setBusy(true);
    setErr(null);
    try {
      await updateRide(rideId, body);
      await load();
      onChanged?.();
    } catch {
      setErr("action");
    } finally {
      setBusy(false);
    }
  };
  const changeStatus = (status: string) => patch({ status });

  const capture = async () => {
    if (!ride?.payment) return;
    setBusy(true);
    setErr(null);
    try {
      await capturePayment(ride.payment.id);
      await load();
      onChanged?.();
    } catch {
      setErr("capture");
    } finally {
      setBusy(false);
    }
  };

  const bucket = ride ? uiStatus(ride.status) : "upcoming";
  const canEnRoute = ["requested", "quoted", "confirmed", "assigned"].includes(ride?.status || "");
  const canComplete = ride?.status === "en_route";
  const canCancel = bucket === "upcoming" || bucket === "active";
  const pay = ride?.payment;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 70,
        background: "rgba(5,5,9,0.72)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 460,
          maxHeight: "88dvh",
          overflowY: "auto",
          background: "var(--obsidian)",
          border: "1px solid var(--volt-border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-volt)",
          padding: 24,
          position: "relative",
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          style={{ position: "absolute", top: 16, right: 16, background: "none", border: "none", cursor: "pointer", padding: 4 }}
        >
          <Icon name="x" size={18} color="var(--silver)" />
        </button>

        {!ride ? (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
            {err ? t("dash.ride.loadErr") : t("common.loading")}
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--arctic)" }}>
                {ride.client?.name || ride.passenger_name || t("dash.ride.guest")}
              </span>
              <StatusPill status={bucket} />
            </div>
            <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 16 }}>BV-{ride.id}</div>

            <div style={{ display: "flex", flexDirection: "column", gap: 11, marginBottom: 18 }}>
              <Row icon="circle-dot">{ride.pickup}</Row>
              <Row icon="map-pin">{ride.dropoff}</Row>
              <Row icon="calendar">{fmtWhen(ride.scheduled_at)}</Row>
              {ride.google_event_id && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--success)" }}>
                  <Icon name="circle-check" size={14} color="var(--success)" />
                  {t("dash.ride.onCalendar")}
                </div>
              )}
              {ride.distance_miles != null && (
                <Row icon="navigation">
                  {ride.distance_miles} mi · {ride.duration_minutes != null ? `${Math.round(ride.duration_minutes)} min` : "—"}
                </Row>
              )}
              {ride.pax != null && <Row icon="users">{ride.pax}</Row>}
              {ride.flight_number && <Row icon="plane">{ride.flight_number}</Row>}
              {(ride.client?.phone || ride.client_phone) && (
                <Row icon="phone">{ride.client?.phone || ride.client_phone}</Row>
              )}
              {ride.notes && <Row icon="message-circle">{ride.notes}</Row>}
            </div>

            {/* Fare + payment */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "14px 16px",
                borderRadius: "var(--radius-md)",
                background: "var(--obsidian-3)",
                border: "1px solid var(--line-strong)",
                marginBottom: 16,
              }}
            >
              <div>
                <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("book.fare")}</div>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--volt)" }}>
                  ${Math.round(ride.fare_total || 0)}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.ride.payment")}</div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: ride.paid ? "var(--success)" : "var(--fg3)" }}>
                  {ride.paid ? t("dash.ride.paidYes") : t("dash.ride.paidNo")}
                  {pay?.simulated ? " ·sim" : ""}
                </div>
              </div>
            </div>

            {/* Payment method + mark paid */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>{t("dash.ride.method")}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                {METHODS.map((m) => {
                  const on = (ride.payment_method || "cash") === m;
                  return (
                    <button
                      key={m}
                      disabled={busy}
                      onClick={() => patch({ payment_method: m })}
                      style={{
                        padding: "7px 13px",
                        borderRadius: "var(--radius-full)",
                        cursor: "pointer",
                        fontSize: 12.5,
                        fontWeight: 600,
                        fontFamily: "var(--font-sans)",
                        background: on ? "var(--volt-bg-20)" : "var(--obsidian-3)",
                        color: on ? "var(--volt)" : "var(--silver)",
                        border: `1px solid ${on ? "var(--volt-border)" : "var(--line-strong)"}`,
                      }}
                    >
                      {t(`dash.method.${m}`)}
                    </button>
                  );
                })}
              </div>
              <button
                disabled={busy}
                onClick={() => patch({ paid: !ride.paid })}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "9px 14px",
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                  fontSize: 13.5,
                  fontWeight: 600,
                  fontFamily: "var(--font-sans)",
                  width: "100%",
                  justifyContent: "center",
                  background: ride.paid ? "rgba(43,212,160,0.12)" : "var(--obsidian-3)",
                  color: ride.paid ? "var(--success)" : "var(--silver)",
                  border: `1px solid ${ride.paid ? "rgba(43,212,160,0.4)" : "var(--line-strong)"}`,
                }}
              >
                <Icon name={ride.paid ? "circle-check" : "circle-dot"} size={16} color="currentColor" />
                {ride.paid ? t("dash.ride.markUnpaid") : t("dash.ride.markPaid")}
              </button>
            </div>

            {err && (
              <div style={{ fontSize: 12.5, color: "var(--danger)", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="alert-circle" size={14} color="var(--danger)" />
                {t(`dash.ride.err.${err}`)}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {pay?.status === "authorized" && (
                <Button variant="solid" icon="credit-card" disabled={busy} onClick={capture}>
                  {t("dash.ride.capture")}
                </Button>
              )}
              {canEnRoute && (
                <Button variant="tint" icon="navigation" disabled={busy} onClick={() => changeStatus("en_route")}>
                  {t("dash.ride.enroute")}
                </Button>
              )}
              {canComplete && (
                <Button variant="solid" icon="circle-check" disabled={busy} onClick={() => changeStatus("completed")}>
                  {t("dash.ride.complete")}
                </Button>
              )}
              {canCancel && (
                <Button variant="ghost" icon="x" disabled={busy} onClick={() => changeStatus("cancelled")}>
                  {t("dash.ride.cancel")}
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
