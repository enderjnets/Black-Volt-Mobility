"use client";

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Card, Field } from "../ui";
import { AddressField } from "./AddressField";
import { SquareCard } from "./SquareCard";
import { RidePreferencesFields } from "./RidePreferences";
import { BVDatePicker, BVTimePicker } from "../DateTimePicker";
import { useI18n } from "@/lib/i18n";
import { buildScheduledAt } from "@/lib/datetime";
import { ApiError, confirmRide, createRide, getQuote, validateDiscount, type Quote } from "@/lib/booking";
import { defaultRidePreferences, getProfile, type RidePreferences } from "@/lib/profile";
import { authorizePayment, getPaymentsConfig, type PaymentsConfig } from "@/lib/payments";
import { pixelTrack, pixelTrackCustom, purchaseEventId, track } from "@/lib/analytics";
import { setRef } from "@/lib/referral";
import { useWeb } from "./WebShell";

const FUNNEL_EVENT = ["book_start", "book_review", "book_pay", "book_confirmed"] as const;

/** Format an ISO instant as a readable Denver-local time (e.g. "Sat, 8:30 PM"). */
function fmtReturn(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: "America/Denver", weekday: "short", hour: "numeric", minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

// Fire a funnel stage at most once per browser session, so page reloads and
// back-and-forth navigation don't inflate stage counts (which would make the
// conversion math read worse than reality). Keyed off sessionStorage (per tab).
function trackFunnelOnce(ev: string, props?: Record<string, unknown>) {
  if (typeof window !== "undefined") {
    try {
      const KEY = "bv_funnel_fired";
      const fired = (sessionStorage.getItem(KEY) || "").split(",").filter(Boolean);
      if (fired.includes(ev)) return;
      fired.push(ev);
      sessionStorage.setItem(KEY, fired.join(","));
    } catch {
      // sessionStorage blocked (private mode) → fall through and still track once.
    }
  }
  track(ev, props);
}

export function MapPlaceholder({ height = 200 }: { height?: number }) {
  return (
    <div
      style={{
        position: "relative",
        height,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: "1px solid var(--line-strong)",
        background:
          "repeating-linear-gradient(0deg, rgba(199,203,212,0.04) 0 1px, transparent 1px 28px), repeating-linear-gradient(90deg, rgba(199,203,212,0.04) 0 1px, transparent 1px 28px), var(--obsidian)",
      }}
    >
      <svg
        viewBox="0 0 320 200"
        preserveAspectRatio="none"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      >
        <path
          d="M40 160 C 110 150, 120 70, 200 60 S 280 40, 286 36"
          fill="none"
          stroke="#00E5FF"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeOpacity="0.9"
        />
      </svg>
      <div style={{ position: "absolute", left: 30, bottom: 48 }}>
        <Icon name="circle-dot" size={18} color="var(--volt)" />
      </div>
      <div style={{ position: "absolute", right: 26, top: 22 }}>
        <Icon name="map-pin" size={20} color="var(--volt)" fill="rgba(0,229,255,0.15)" />
      </div>
    </div>
  );
}

function StepDots({ step }: { step: number }) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: i === step ? 22 : 7,
            height: 7,
            borderRadius: 99,
            background: i <= step ? "var(--volt)" : "var(--obsidian-3)",
            transition: "all .2s ease-out",
          }}
        />
      ))}
    </div>
  );
}

function Stat({ icon, label, value, accent }: { icon: string; label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ flex: 1 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          color: "var(--fg3)",
          fontSize: 12,
          marginBottom: 6,
          fontFamily: "var(--font-sans)",
        }}
      >
        <Icon name={icon} size={14} color="var(--silver)" /> {label}
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 26,
          color: accent ? "var(--volt)" : "var(--arctic)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
    </div>
  );
}

export function Booking() {
  const { t, lang } = useI18n();
  const { openSignIn } = useWeb();
  const [step, setStep] = useState(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("Denver Intl (DEN)");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [schedErr, setSchedErr] = useState(false);
  const [pax, setPax] = useState(2);
  const [roundTrip, setRoundTrip] = useState(false);
  const [returnAt, setReturnAt] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoting, setQuoting] = useState(false);
  // Registration wall: a 401 on /quote means the visitor must sign in first
  // (which also attributes them to their referring driver). `reload` re-runs the
  // quote after they authenticate.
  const [authWall, setAuthWall] = useState(false);
  const [reload, setReload] = useState(0);
  const [rideId, setRideId] = useState<number | null>(null);
  const [payCfg, setPayCfg] = useState<PaymentsConfig | null>(null);
  const [paying, setPaying] = useState(false);
  const [payErr, setPayErr] = useState<string | null>(null);
  // Payment choice at the pay step: "now" (card via Square) or "later" (pay the
  // driver at drop-off — no online charge). `payLater` drives the confirmation copy.
  const [payMode, setPayMode] = useState<"now" | "later">("now");
  const [payLater, setPayLater] = useState(false);
  // Per-ride preferences, prefilled from the rider's standing prefs (if signed in).
  const [ridePrefs, setRidePrefs] = useState<RidePreferences>(defaultRidePreferences());
  const [showPrefs, setShowPrefs] = useState(false);
  // Discount code
  const [code, setCode] = useState("");
  const [appliedCode, setAppliedCode] = useState("");
  const [codePct, setCodePct] = useState(0);
  const [codeErr, setCodeErr] = useState<string | null>(null);
  const [codeApplying, setCodeApplying] = useState(false);

  // Driver attribution across the host boundary: a customer arriving from a
  // driver's profile (served on the `app.` dashboard host) lands here on the apex
  // booking host with `?ref=<slug>`. The referral cookie is host-scoped so it
  // doesn't survive the jump — persist the slug from the URL before any quote or
  // sign-in so the registration wall binds the lead to that driver and prices
  // against their rate. `setRef` ignores malformed slugs.
  useEffect(() => {
    const qp = new URLSearchParams(window.location.search);
    const ref = qp.get("ref");
    if (ref) setRef(ref);
    // Prefill the trip from a deep-link (e.g. SEO route landing pages → /book?from=&to=)
    // so the visitor lands straight on a quote.
    const qpFrom = qp.get("from");
    const qpTo = qp.get("to");
    if (qpFrom) setFrom(qpFrom);
    if (qpTo) setTo(qpTo);
    // Prefill the event date/time so the quote matches the event and applies its fees.
    const qpDate = qp.get("date");
    const qpTime = qp.get("time");
    if (qpDate) setDate(qpDate);
    if (qpTime) setTime(qpTime);
    // Round trip deep-link from an event landing (?rt=1&return_at=…).
    if (qp.get("rt") === "1") setRoundTrip(true);
    const qpReturn = qp.get("return_at");
    if (qpReturn) setReturnAt(qpReturn);
  }, []);

  // Booking-funnel analytics: each stage counts at most once per session. `book_review`
  // is fired when the price is actually shown (in the quote effect below), not just on
  // reaching the step — so "reviewed route" reflects riders who really saw a fare.
  useEffect(() => {
    const ev = FUNNEL_EVENT[step];
    if (ev && ev !== "book_review") {
      trackFunnelOnce(ev, ev === "book_confirmed" ? { fare: quote?.total } : undefined);
    }
    // Meta Pixel funnel: InitiateCheckout at the payment step, Purchase on confirm
    // (deduped with the server CAPI by eventID). QuoteViewed fires with book_review.
    if (ev === "book_pay") {
      pixelTrack("InitiateCheckout", { value: quote?.total, currency: "USD" });
    } else if (ev === "book_confirmed" && rideId != null) {
      pixelTrack(
        "Purchase",
        { value: quote?.total, currency: "USD" },
        purchaseEventId(rideId),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // Real fare/route from the backend (Distance Matrix + pricing engine) when the
  // rider reaches the review step. Falls back to the mock display if it fails.
  useEffect(() => {
    if (step !== 1) return;
    const pickup = (from || "Downtown Denver").trim();
    const dropoff = to.trim();
    if (!pickup || !dropoff) return;
    let alive = true;
    setQuoting(true);
    setAuthWall(false);
    getQuote({ pickup, dropoff, pax, scheduled_at: date ? buildScheduledAt(date, time) : null, ...(roundTrip ? { round_trip: true, return_at: returnAt } : {}), ...(appliedCode ? { discount_code: appliedCode } : {}) })
      .then((q) => {
        if (alive) {
          setQuote(q);
          trackFunnelOnce("book_review"); // price shown = route actually reviewed
          pixelTrackCustom("QuoteViewed", { value: q.total, currency: "USD" });
        }
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setQuote(null);
        // Registration wall → prompt sign-in, then re-fetch the quote.
        if (e instanceof ApiError && e.status === 401) {
          setAuthWall(true);
          openSignIn(() => {
            setAuthWall(false);
            setReload((n) => n + 1);
          });
        }
      })
      .finally(() => {
        if (alive) setQuoting(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, from, to, pax, reload, appliedCode, roundTrip, returnAt]);

  // Display helpers — real quote when available, else the original mock values.
  const fareText = quote ? `$${Math.round(quote.total)}` : quoting ? "—" : "$120";
  const distanceText = quote ? `${quote.distance_miles} mi` : quoting ? "—" : "18.4 mi";
  const etaText = quote ? `${Math.round(quote.duration_minutes)} min` : quoting ? "—" : "6 min";

  // Load payments config once → decides real Square card form vs simulated fallback.
  useEffect(() => {
    getPaymentsConfig().then(setPayCfg).catch(() => setPayCfg(null));
  }, []);

  // Prefill ride preferences from the rider's standing prefs (ignored if not signed in).
  useEffect(() => {
    getProfile()
      .then((p) => setRidePrefs(p.ride_preferences ?? defaultRidePreferences()))
      .catch(() => {});
  }, [reload]);
  const squareReady = !!(payCfg && payCfg.application_id && payCfg.location_id);

  // Discount code validation and re-quote.
  const handleApplyCode = async () => {
    if (!code || codeApplying) return;
    setCodeApplying(true);
    setCodeErr(null);
    try {
      const res = await validateDiscount(code);
      if (!res.valid) { setCodeErr(t("book.discount.invalid")); return; }
      setCodePct(res.discount_pct);
      setAppliedCode(code); // triggers re-quote via useEffect dep
    } catch (e: unknown) {
      setCodePct(0);
      setAppliedCode("");
      if (e instanceof ApiError) {
        if (e.status === 410) setCodeErr(t("book.discount.expired"));
        else setCodeErr(t("book.discount.invalid"));
      } else {
        setCodeErr(t("book.discount.neterr"));
      }
    } finally {
      setCodeApplying(false);
    }
  };

  // Step 1 → 2: create the ride (QUOTED) so the payment can attach to it.
  const proceedToPay = async () => {
    if (paying) return;
    setPaying(true);
    setPayErr(null);
    try {
      if (rideId == null) {
        const ride = await createRide({
          pickup: (from || "Downtown Denver").trim(),
          dropoff: to.trim(),
          pax,
          scheduled_at: date ? buildScheduledAt(date, time) : null,
          ride_preferences: ridePrefs,
          ...(roundTrip ? { round_trip: true, return_at: returnAt } : {}),
          ...(appliedCode ? { discount_code: appliedCode } : {}),
          confirm: false,
        });
        setRideId(ride.id);
      }
      setStep(2);
    } catch (e) {
      // Registration wall lives HERE now: anyone can see the price; signing in is only
      // required to actually book. Bind the lead to the driver (?ref/cookie), then retry.
      if (e instanceof ApiError && e.status === 401) {
        setPaying(false);
        openSignIn(() => {
          setReload((n) => n + 1);
          void proceedToPay();
        });
        return;
      }
      track("book_pay_failed", { reason: "ride" });
      setPayErr("ride");
    } finally {
      setPaying(false);
    }
  };

  // Pay-on-completion: confirm the ride without an online charge. The driver
  // collects (cash or their own Square) at drop-off. Moves the ride to CONFIRMED
  // and onto the driver's calendar.
  const handlePayLater = async () => {
    if (rideId == null) {
      setPayErr("ride");
      return;
    }
    if (paying) return;
    setPaying(true);
    setPayErr(null);
    try {
      await confirmRide(rideId);
      setPayLater(true);
      setStep(3);
    } catch {
      track("book_pay_failed", { reason: "confirm" });
      setPayErr("ride");
    } finally {
      setPaying(false);
    }
  };

  // Card token (Square) or simulated nonce → authorize → confirmed.
  const handleToken = async (token: string) => {
    if (rideId == null) {
      setPayErr("ride");
      return;
    }
    setPaying(true);
    setPayErr(null);
    try {
      await authorizePayment({ ride_id: rideId, source_id: token });
      setStep(3);
    } catch {
      track("book_pay_failed", { reason: "declined" });
      setPayErr("declined");
    } finally {
      setPaying(false);
    }
  };

  return (
    <div style={{ maxWidth: 480, margin: "0 auto", padding: "32px 0" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 28, color: "var(--arctic)", margin: 0 }}>
          {step === 3 ? t("book.confirmed") : t("book.title")}
        </h2>
        {step < 3 && <StepDots step={step} />}
      </div>

      {step === 0 && (
        <p style={{ fontSize: 13, color: "var(--fg3)", margin: "-6px 0 14px", lineHeight: 1.5 }}>
          {t("book.coverage")}
        </p>
      )}

      <Card glow pad={22}>
        {step === 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <AddressField icon="circle-dot" label={t("book.from")} value={from} placeholder={t("book.from.ph")} onChange={setFrom} />
            <AddressField icon="plane" label={t("book.to")} value={to} placeholder={t("book.to.ph")} onChange={setTo} />
            <div style={{ width: 120 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{t("book.pax")}</div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)",
                  borderRadius: "var(--radius-md)",
                  padding: "6px 10px",
                }}
              >
                <button
                  onClick={() => setPax(Math.max(1, pax - 1))}
                  style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
                >
                  –
                </button>
                <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--arctic)", fontSize: 16 }}>
                  {pax}
                </span>
                <button
                  onClick={() => setPax(Math.min(6, pax + 1))}
                  style={{ background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
                >
                  +
                </button>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t("book.when")}</div>
              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <BVDatePicker
                    label={t("book.date")}
                    value={date}
                    onChange={(v) => {
                      setDate(v);
                      setSchedErr(false);
                    }}
                    lang={lang}
                    state={schedErr && !date ? "missing" : "normal"}
                    half
                    required
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <BVTimePicker label={t("book.time")} value={time} onChange={setTime} lang={lang} half required />
                </div>
              </div>
              {schedErr && !date && (
                <div style={{ fontSize: 12.5, color: "var(--danger)", display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon name="alert-circle" size={14} color="var(--danger)" />
                  {t("book.sched.err")}
                </div>
              )}
            </div>
            <label
              style={{
                display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
                padding: "10px 0",
              }}
            >
              <input
                type="checkbox"
                checked={roundTrip}
                onChange={(e) => setRoundTrip(e.target.checked)}
                style={{ width: 18, height: 18, accentColor: "var(--volt)" }}
              />
              <span>
                <span style={{ fontWeight: 600 }}>{t("book.roundtrip")}</span>
                <span style={{ display: "block", fontSize: 12, color: "var(--fg3)" }}>
                  {t("book.roundtrip.hint")}
                </span>
              </span>
            </label>
            {roundTrip && to ? (
              <div
                style={{
                  fontSize: 12, color: "var(--silver)", background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)", borderRadius: 10,
                  padding: "10px 12px", marginBottom: 12, lineHeight: 1.5,
                }}
              >
                {t("book.roundtrip.return")
                  .replace("{venue}", to)
                  .replace("{time}", returnAt ? fmtReturn(returnAt) : t("book.roundtrip.afterShow"))}
              </div>
            ) : null}
            <Button
              variant="solid"
              full
              size="lg"
              iconRight="arrow-right"
              onClick={() => {
                if (!date) {
                  setSchedErr(true);
                  return;
                }
                setStep(1);
              }}
            >
              {t("book.review")}
            </Button>
          </div>
        )}

        {step === 1 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <MapPlaceholder height={190} />
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--silver)" }}>
                <Icon name="circle-dot" size={16} color="var(--volt)" /> {from || "Downtown Denver"}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: "var(--silver)" }}>
                <Icon name="plane" size={16} color="var(--volt)" /> {to}
              </div>
            </div>
            {authWall ? (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 12,
                  borderTop: "1px solid var(--line)",
                  paddingTop: 18,
                  textAlign: "center",
                }}
              >
                <Icon name="lock" size={22} color="var(--volt)" />
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 17, color: "var(--arctic)" }}>
                  {t("book.wall.title")}
                </div>
                <p style={{ fontSize: 13.5, color: "var(--silver)", margin: 0, lineHeight: 1.5, maxWidth: 320 }}>
                  {t("book.wall.sub")}
                </p>
                <div style={{ display: "flex", gap: 10, width: "100%" }}>
                  <Button variant="plain" icon="arrow-left" onClick={() => setStep(0)}>
                    {t("common.back")}
                  </Button>
                  <Button
                    variant="solid"
                    full
                    icon="zap"
                    onClick={() =>
                      openSignIn(() => {
                        setAuthWall(false);
                        setReload((n) => n + 1);
                      })
                    }
                  >
                    {t("book.wall.cta")}
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 16, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
                  <Stat icon="navigation" label={t("book.distance")} value={distanceText} />
                  <Stat icon="clock" label={t("book.eta")} value={etaText} />
                  <Stat icon="dollar-sign" label={t("book.fare")} value={fareText} accent />
                </div>

                {quote?.zone_name && (
                  <div
                    style={{
                      marginTop: 10,
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      fontSize: 12.5,
                      color: "var(--volt)",
                    }}
                  >
                    <Icon name="map-pin" size={13} color="var(--volt)" />
                    {t("book.flatRate")} · {quote.zone_name}
                  </div>
                )}

                {/* Discount code */}
                <div style={{ borderTop: "1px solid var(--line)", paddingTop: 16 }}>
                  <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{t("book.discount.label")}</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      type="text"
                      value={code}
                      onChange={(e) => { setCode(e.target.value.toUpperCase()); setCodeErr(null); }}
                      placeholder="PROMO10"
                      disabled={!!appliedCode || codeApplying}
                      style={{
                        flex: 1,
                        background: "var(--obsidian-3)",
                        border: "1px solid var(--line-strong)",
                        borderRadius: "var(--radius-md)",
                        color: "var(--arctic)",
                        fontFamily: "var(--font-sans)",
                        fontSize: 14,
                        padding: "8px 10px",
                        outline: "none",
                      }}
                    />
                    <Button
                      variant="ghost"
                      disabled={!code || !!appliedCode || codeApplying}
                      onClick={handleApplyCode}
                    >
                      {codeApplying ? "…" : t("book.discount.apply")}
                    </Button>
                  </div>
                  {appliedCode && (
                    <div style={{ marginTop: 6, fontSize: 12.5, color: "var(--volt)", display: "flex", alignItems: "center", gap: 6 }}>
                      <Icon name="check" size={14} color="var(--volt)" />
                      {t("book.discount.applied").replace("{pct}", String(codePct))}
                      <button
                        type="button"
                        onClick={() => { setAppliedCode(""); setCode(""); setCodePct(0); setCodeErr(null); }}
                        style={{ marginLeft: 4, background: "none", border: "none", cursor: "pointer", color: "var(--fg3)", fontSize: 12.5, padding: 0 }}
                      >
                        {t("book.discount.remove")}
                      </button>
                    </div>
                  )}
                  {codeErr && (
                    <div style={{ marginTop: 6, fontSize: 12.5, color: "var(--danger)", display: "flex", alignItems: "center", gap: 6 }}>
                      <Icon name="alert-circle" size={14} color="var(--danger)" />
                      {codeErr}
                    </div>
                  )}
                </div>

                <div style={{ borderTop: "1px solid var(--line)", paddingTop: 16 }}>
                  <button
                    type="button"
                    onClick={() => setShowPrefs((s) => !s)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      width: "100%",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      padding: 0,
                      color: "var(--silver)",
                      fontFamily: "var(--font-sans)",
                      fontSize: 13.5,
                    }}
                  >
                    <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--arctic)", fontWeight: 600 }}>
                        <Icon name="settings" size={16} color="var(--silver)" />
                        {t("book.prefs.title")}
                      </span>
                      <span style={{ fontSize: 11.5, color: "var(--fg3)" }}>{t("book.prefs.hint")}</span>
                    </span>
                    <Icon name={showPrefs ? "chevron-up" : "chevron-down"} size={16} color="var(--silver)" />
                  </button>
                  {showPrefs && (
                    <div style={{ marginTop: 14 }}>
                      <RidePreferencesFields
                        value={ridePrefs}
                        onChange={(patch) => setRidePrefs((cur) => ({ ...cur, ...patch }))}
                      />
                    </div>
                  )}
                </div>

                <div style={{ display: "flex", gap: 10 }}>
                  <Button variant="plain" icon="arrow-left" onClick={() => setStep(0)}>
                    {t("common.back")}
                  </Button>
                  <Button variant="solid" full iconRight="arrow-right" disabled={paying} onClick={proceedToPay}>
                    {paying ? t("pay.processing") : t("book.pay")}
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {step === 2 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ color: "var(--silver)", fontSize: 14 }}>{t("book.fare")}</span>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 32, color: "var(--arctic)" }}>
                ${(quote ? quote.total : 120).toFixed(2)}
              </span>
            </div>
            {quote?.event ? (
              <div
                style={{
                  fontSize: 12, color: "var(--silver)", background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)",
                  padding: "10px 12px", marginBottom: 12, lineHeight: 1.5,
                }}
              >
                {t("book.event.prepaid")}
              </div>
            ) : null}
            {/* Pay now (card) vs pay the driver at drop-off (cash, no online charge). */}
            <div
              role="tablist"
              style={{
                display: "flex",
                gap: 6,
                background: "var(--obsidian-3)",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--radius-md)",
                padding: 4,
              }}
            >
              {((quote?.event ? ["now"] : ["now", "later"]) as ("now" | "later")[]).map((m) => {
                const active = payMode === m;
                return (
                  <button
                    key={m}
                    role="tab"
                    aria-selected={active}
                    onClick={() => {
                      setPayMode(m);
                      setPayErr(null);
                    }}
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
                    {t(m === "now" ? "book.paynow" : "book.paylater")}
                  </button>
                );
              })}
            </div>

            {payMode === "now" || quote?.event ? (
              squareReady ? (
                <SquareCard
                  applicationId={payCfg!.application_id!}
                  locationId={payCfg!.location_id!}
                  env={payCfg!.env}
                  sandbox={!payCfg!.live}
                  amountLabel={`$${(quote ? quote.total : 120).toFixed(2)}`}
                  onToken={handleToken}
                />
              ) : (
                <>
                  <Field icon="credit-card" label={t("pay.card")} value="•••• •••• •••• 4242" readOnly />
                  <Button
                    variant="solid"
                    full
                    size="lg"
                    icon="zap"
                    disabled={paying}
                    onClick={() => handleToken("cnon:card-nonce-ok")}
                  >
                    {paying ? t("pay.processing") : t("book.paybtn")}
                  </Button>
                </>
              )
            ) : (
              <>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: 13.5,
                    color: "var(--silver)",
                    lineHeight: 1.5,
                  }}
                >
                  <Icon name="dollar-sign" size={18} color="var(--volt)" />
                  {t("book.paylater.note").replace("{amount}", `$${(quote ? quote.total : 120).toFixed(2)}`)}
                </div>
                <Button
                  variant="solid"
                  full
                  size="lg"
                  icon="check"
                  disabled={paying}
                  onClick={handlePayLater}
                >
                  {paying ? t("pay.processing") : t("book.paylater.confirm")}
                </Button>
              </>
            )}
            {payErr && (
              <div style={{ fontSize: 12.5, color: "var(--danger)", display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="alert-circle" size={14} color="var(--danger)" />
                {t(`pay.err.${payErr}`)}
              </div>
            )}
            <div
              style={{
                textAlign: "center",
                fontSize: 11,
                color: "var(--fg3)",
                textTransform: "uppercase",
                letterSpacing: "0.18em",
                fontFamily: "var(--font-display)",
                fontWeight: 600,
              }}
            >
              {t("book.silent")}
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ textAlign: "center", padding: "10px 0 6px" }}>
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                margin: "0 auto 18px",
                background: "var(--volt-bg)",
                border: "1px solid var(--volt-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "var(--shadow-volt)",
              }}
            >
              <Icon name="check" size={32} color="var(--volt)" />
            </div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: 22,
                color: "var(--arctic)",
                marginBottom: 8,
              }}
            >
              {t("book.confirmed")}
            </div>
            <p style={{ color: "var(--silver)", fontSize: 14, maxWidth: 300, margin: "0 auto 14px", lineHeight: 1.5 }}>
              {t("book.confirmed.sub")}
            </p>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                background: "var(--volt-bg)",
                border: "1px solid var(--volt-border)",
                borderRadius: "var(--radius-full)",
                padding: "6px 14px",
                marginBottom: 18,
              }}
            >
              <Icon name="message-circle" size={14} color="var(--volt)" />
              <span style={{ fontSize: 12.5, color: "var(--volt)", fontWeight: 600, fontFamily: "var(--font-sans)" }}>{t("book.sms")}</span>
            </div>
            {payLater && (
              <p style={{ color: "var(--silver)", fontSize: 13, maxWidth: 320, margin: "0 auto 14px", lineHeight: 1.5 }}>
                {t("book.confirmed.paylater").replace("{amount}", `$${(quote ? quote.total : 120).toFixed(2)}`)}
              </p>
            )}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 16,
                padding: "14px 0",
                borderTop: "1px solid var(--line)",
                borderBottom: "1px solid var(--line)",
              }}
            >
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--volt)" }}>
                  {quote ? `${Math.round(quote.duration_minutes)} min` : "6 min"}
                </div>
                <div style={{ fontSize: 11, color: "var(--fg3)" }}>ETA</div>
              </div>
              <div style={{ width: 1, height: 30, background: "var(--line-strong)" }} />
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--arctic)" }}>
                  Kia EV9
                </div>
                <div style={{ fontSize: 11, color: "var(--fg3)" }}>Black · ENV-4827</div>
              </div>
            </div>
            <div style={{ marginTop: 18 }}>
              <Button
                variant="ghost"
                full
                onClick={() => {
                  // Fresh booking — don't reuse the just-paid ride or its payment state.
                  setRideId(null);
                  setQuote(null);
                  setPayErr(null);
                  setPayMode("now");
                  setPayLater(false);
                  setStep(0);
                }}
              >
                {t("book.another")}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
