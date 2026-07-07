"use client";

/* Dedicated event reservation flow: round-trip-with-wait ONLY (no one-way).
   The driver takes you to the venue, waits during the show, and brings you home.
   A 1/3 deposit (Square) secures the booking; the balance is paid in person on the day.
   Pickup time is suggested from Google-Maps traffic so you arrive ~30 min before the show.
   Reuses the shared AddressField / SquareCard / booking + payments libs — the generic
   /book funnel is untouched. */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { BookEvent } from "@/app/(web)/events/[slug]/book/page";
import { AddressField } from "@/components/bv/web/AddressField";
import { SquareCard } from "@/components/bv/web/SquareCard";
import { useWeb } from "@/components/bv/web/WebShell";
import { Button } from "@/components/bv/ui";
import { createRide, getQuote, type Quote } from "@/lib/booking";
import { getPickupSuggestion, type PickupSuggestion } from "@/lib/events";
import { useI18n } from "@/lib/i18n";
import { authorizePayment, getPaymentsConfig, type PaymentsConfig } from "@/lib/payments";

type Step = "details" | "review" | "pay" | "done";

const TZ = "America/Denver";

function denverTime(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function denverDate(iso: string, lang: string): string {
  return new Intl.DateTimeFormat(lang === "es" ? "es-US" : "en-US", {
    timeZone: TZ,
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date(iso));
}

function toMin(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

function shiftIso(iso: string, deltaMin: number): string {
  return new Date(new Date(iso).getTime() + deltaMin * 60000).toISOString();
}

function money(n: number): string {
  return `$${n.toFixed(2)}`;
}

// Page-specific bilingual copy (EN/ES) driven by the app language.
function copy(lang: string) {
  const es = lang === "es";
  return {
    heading: es ? "Reserva tu round trip" : "Book your round trip",
    plan: (venue: string) =>
      es
        ? `Te llevamos a ${venue}, tu chofer espera durante el show y te trae de vuelta.`
        : `We take you to ${venue}, your driver waits during the show, and brings you home.`,
    yourPickup: es ? "Tu recogida" : "Your pickup",
    address: es ? "Dirección de recogida" : "Pickup address",
    addressPh: es ? "Tu casa o punto de partida" : "Your home or starting point",
    passengers: es ? "Pasajeros" : "Passengers",
    continue: es ? "Continuar" : "Continue",
    back: es ? "Atrás" : "Back",
    pickupTime: es ? "Hora de recogida" : "Pickup time",
    arriveHint: (mins: number, traffic: boolean) =>
      es
        ? `Llegas ~30 min antes del show. Con ${traffic ? "tráfico" : "el trayecto"} estimado ≈ ${mins} min.`
        : `You arrive ~30 min before the show. ${traffic ? "Traffic-adjusted" : "Estimated"} drive ≈ ${mins} min.`,
    returnHint: (time: string) =>
      es
        ? `Regreso al terminar el show (~${time}); tu chofer te espera.`
        : `Return when the show ends (~${time}); your driver waits for you.`,
    reviewHeading: es ? "Revisa tu reserva" : "Review your reservation",
    roundTripTotal: es ? "Total round trip" : "Round-trip total",
    driverWaits: es ? "El chofer espera · sin surge" : "Driver waits · no surge",
    depositLabel: es ? "Depósito ahora (1/3)" : "Deposit now (1/3)",
    balanceLabel: es ? "Saldo el día del evento" : "Balance on the event day",
    termsHeading: es ? "Términos de tu reserva" : "Reservation terms",
    term1: (d: string, b: string) =>
      es
        ? `Un depósito de ${d} confirma tu reserva; el resto (${b}) se paga el día del evento con tu chofer.`
        : `A ${d} deposit confirms your booking; the rest (${b}) is paid on the event day with your driver.`,
    term2: es
      ? "Cancelación gratis hasta 48 h antes del evento → depósito 100% reembolsable."
      : "Free cancellation up to 48 hours before the event → deposit fully refunded.",
    term3: es
      ? "Dentro de las 48 h previas → el depósito no es reembolsable (tu chofer ya apartó la noche)."
      : "Within 48 hours of the event → the deposit is non-refundable (your driver reserved the night).",
    accept: es ? "He leído y acepto estos términos." : "I've read and agree to these terms.",
    signIn: es ? "Inicia sesión para reservar" : "Sign in to book",
    payDeposit: (d: string) => (es ? `Pagar depósito ${d}` : `Pay deposit ${d}`),
    paymentHeading: es ? "Paga tu depósito" : "Pay your deposit",
    oneCharge: es
      ? "Un solo cargo ahora por el depósito. El saldo se paga en persona."
      : "One charge now for the deposit. The balance is paid in person.",
    confirmedHeading: es ? "¡Reserva confirmada!" : "You're booked!",
    confirmedBody: (b: string) =>
      es
        ? `Tu round trip está reservado. El saldo (${b}) se paga el día del evento con tu chofer.`
        : `Your round trip is reserved. The balance (${b}) is paid on the event day with your driver.`,
    loading: es ? "Calculando…" : "Working…",
  };
}

export default function EventBooking({ ev }: { ev: BookEvent }) {
  const { lang } = useI18n();
  const { user, openSignIn } = useWeb();
  const c = useMemo(() => copy(lang), [lang]);

  const venue = ev.venue_address ? `${ev.venue_name}, ${ev.venue_address}` : ev.venue_name;

  const [step, setStep] = useState<Step>("details");
  const [address, setAddress] = useState("");
  const [pax, setPax] = useState(2);
  const [sug, setSug] = useState<PickupSuggestion | null>(null);
  const [pickupTime, setPickupTime] = useState<string>("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [cfg, setCfg] = useState<PaymentsConfig | null>(null);
  const [rideId, setRideId] = useState<number | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getPaymentsConfig().then(setCfg).catch(() => setCfg(null));
  }, []);

  // The chosen pickup instant: the suggested ISO shifted by the user's edit to the local time.
  const scheduledIso = useMemo(() => {
    if (!sug) return null;
    const base = denverTime(sug.pickup_at);
    const delta = pickupTime ? toMin(pickupTime) - toMin(base) : 0;
    return shiftIso(sug.pickup_at, delta);
  }, [sug, pickupTime]);

  const total = quote?.total ?? 0;
  const deposit = Math.round((total / 3) * 100) / 100;
  const balance = Math.round((total - deposit) * 100) / 100;

  const loadReview = useCallback(async () => {
    if (!address.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const s = await getPickupSuggestion(ev.slug, address.trim());
      setSug(s);
      setPickupTime(denverTime(s.pickup_at));
      const q = await getQuote({
        pickup: address.trim(),
        dropoff: venue,
        scheduled_at: s.pickup_at,
        round_trip: true,
        return_at: ev.return_at,
        pax,
      });
      setQuote(q);
      setStep("review");
    } catch {
      setErr(lang === "es" ? "No pudimos calcular tu viaje. Revisa la dirección." : "We couldn't price your trip. Check the address.");
    } finally {
      setBusy(false);
    }
  }, [address, ev.slug, ev.return_at, venue, pax, lang]);

  // Re-quote when the rider edits the pickup time (a later leg can cross the night cutoff).
  const reprice = useCallback(async () => {
    if (!scheduledIso) return;
    try {
      const q = await getQuote({
        pickup: address.trim(),
        dropoff: venue,
        scheduled_at: scheduledIso,
        round_trip: true,
        return_at: ev.return_at,
        pax,
      });
      setQuote(q);
    } catch {
      /* keep the prior quote on a transient failure */
    }
  }, [scheduledIso, address, venue, ev.return_at, pax]);

  const startPayment = useCallback(async () => {
    if (!scheduledIso || !agreed) return;
    if (!user) {
      openSignIn();
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const ride = await createRide({
        pickup: address.trim(),
        dropoff: venue,
        scheduled_at: scheduledIso,
        round_trip: true,
        return_at: ev.return_at,
        pax,
        terms_accepted: true,
        confirm: false,
      });
      setRideId(ride.id);
      setStep("pay");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [scheduledIso, agreed, user, openSignIn, address, venue, ev.return_at, pax]);

  const onToken = useCallback(
    async (token: string) => {
      if (!rideId) return;
      setBusy(true);
      setErr(null);
      try {
        await authorizePayment({ ride_id: rideId, source_id: token });
        setStep("done");
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [rideId],
  );

  const wrap: React.CSSProperties = { maxWidth: 640, margin: "0 auto", padding: "24px 16px" };
  const card: React.CSSProperties = {
    background: "var(--card, rgba(255,255,255,0.03))",
    border: "1px solid var(--border, rgba(255,255,255,0.1))",
    borderRadius: 16,
    padding: 20,
    marginTop: 16,
  };
  const label: React.CSSProperties = { fontSize: 13, opacity: 0.75, marginBottom: 6 };

  return (
    <main style={wrap}>
      <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>{c.heading}</h1>
      <p style={{ opacity: 0.85, marginTop: 6 }}>{ev.title}</p>
      <p style={{ opacity: 0.7, fontSize: 14, marginTop: 4 }}>{c.plan(ev.venue_name)}</p>

      {err ? <p style={{ color: "#ff6b6b", marginTop: 12 }}>{err}</p> : null}

      {step === "details" && (
        <div style={card}>
          <div style={{ fontWeight: 700, marginBottom: 12 }}>{c.yourPickup}</div>
          <div style={label}>{c.address}</div>
          <AddressField value={address} onChange={setAddress} placeholder={c.addressPh} />
          <div style={{ ...label, marginTop: 16 }}>{c.passengers}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Button onClick={() => setPax((p) => Math.max(1, p - 1))}>−</Button>
            <span style={{ minWidth: 24, textAlign: "center", fontWeight: 700 }}>{pax}</span>
            <Button onClick={() => setPax((p) => Math.min(6, p + 1))}>+</Button>
          </div>
          <div style={{ marginTop: 20 }}>
            <Button onClick={loadReview} disabled={!address.trim() || busy}>
              {busy ? c.loading : c.continue}
            </Button>
          </div>
        </div>
      )}

      {step === "review" && sug && quote && (
        <>
          <div style={card}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>{c.yourPickup}</div>
            <div style={{ opacity: 0.8, fontSize: 14 }}>{denverDate(ev.starts_at, lang)}</div>
            <div style={{ ...label, marginTop: 14 }}>{c.pickupTime}</div>
            <input
              type="time"
              value={pickupTime}
              onChange={(e) => setPickupTime(e.target.value)}
              onBlur={reprice}
              style={{
                background: "transparent",
                border: "1px solid var(--border, rgba(255,255,255,0.2))",
                borderRadius: 10,
                padding: "10px 12px",
                color: "inherit",
                fontSize: 16,
              }}
            />
            <p style={{ opacity: 0.7, fontSize: 13, marginTop: 8 }}>
              {c.arriveHint(sug.travel_minutes_out, sug.traffic_aware)}
            </p>
            <p style={{ opacity: 0.7, fontSize: 13, marginTop: 4 }}>
              {c.returnHint(denverTime(sug.return_pickup_at))}
            </p>
          </div>

          <div style={card}>
            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700 }}>
              <span>{c.roundTripTotal}</span>
              <span>{money(total)}</span>
            </div>
            <div style={{ opacity: 0.7, fontSize: 13, marginTop: 2 }}>{c.driverWaits}</div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14 }}>
              <span style={{ opacity: 0.85 }}>{c.depositLabel}</span>
              <span style={{ fontWeight: 700 }}>{money(deposit)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              <span style={{ opacity: 0.85 }}>{c.balanceLabel}</span>
              <span>{money(balance)}</span>
            </div>
          </div>

          <div style={card}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>{c.termsHeading}</div>
            <ul style={{ margin: 0, paddingLeft: 18, opacity: 0.85, fontSize: 14, lineHeight: 1.6 }}>
              <li>{c.term1(money(deposit), money(balance))}</li>
              <li>{c.term2}</li>
              <li>{c.term3}</li>
            </ul>
            <label style={{ display: "flex", gap: 10, alignItems: "flex-start", marginTop: 14, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span style={{ fontSize: 14 }}>{c.accept}</span>
            </label>
          </div>

          <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
            <Button onClick={() => setStep("details")}>{c.back}</Button>
            <Button onClick={startPayment} disabled={!agreed || busy}>
              {busy ? c.loading : user ? c.payDeposit(money(deposit)) : c.signIn}
            </Button>
          </div>
        </>
      )}

      {step === "pay" && (
        <div style={card}>
          <div style={{ fontWeight: 700 }}>{c.paymentHeading}</div>
          <p style={{ opacity: 0.75, fontSize: 14, marginTop: 6 }}>{c.oneCharge}</p>
          {cfg && cfg.live && cfg.application_id && cfg.location_id ? (
            <div style={{ marginTop: 12 }}>
              <SquareCard
                applicationId={cfg.application_id}
                locationId={cfg.location_id}
                env={cfg.env}
                sandbox={cfg.env !== "production"}
                amountLabel={c.payDeposit(money(deposit))}
                onToken={onToken}
              />
            </div>
          ) : (
            // Simulated Square (dev / not configured): a fixed test nonce, never a live charge.
            <div style={{ marginTop: 12 }}>
              <Button onClick={() => onToken("cnon:card-nonce-ok")} disabled={busy}>
                {busy ? c.loading : c.payDeposit(money(deposit))}
              </Button>
            </div>
          )}
        </div>
      )}

      {step === "done" && (
        <div style={card}>
          <div style={{ fontSize: 20, fontWeight: 800 }}>✓ {c.confirmedHeading}</div>
          <p style={{ opacity: 0.85, marginTop: 8 }}>{c.confirmedBody(money(balance))}</p>
        </div>
      )}
    </main>
  );
}
