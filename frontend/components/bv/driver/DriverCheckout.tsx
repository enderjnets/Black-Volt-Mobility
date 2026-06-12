"use client";

/* Operator subscription checkout modal. Fetches the PUBLIC payments config,
   mounts the Square card iframe, and on pay validates the email, tokenizes the
   card, and posts {plan_key, source_id, email} to /subscriptions. Card data
   never reaches our backend. If Square isn't configured yet it degrades to a
   "contact us" state, exactly like the original landing. */

import { useEffect, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { getPaymentsConfig } from "@/lib/payments";
import { loadSquareSdk, type SquareCardObj, type SquarePayments } from "@/lib/squareSdk";
import { subscribe } from "@/lib/subscriptions";

type Phase = "loading" | "ready" | "degraded" | "done";
type MsgKind = "info" | "err" | "ok";

const KNOWN_ERRORS = new Set([
  "invalid_plan",
  "rate_limited",
  "subscriptions_unavailable",
  "account_disabled",
  "subscription_conflict",
  "card_invalid",
]);

export function DriverCheckout({
  open,
  onClose,
  planKey,
  priceLabel,
  salesEmail,
}: {
  open: boolean;
  onClose: () => void;
  planKey: string;
  priceLabel: string;
  salesEmail: string;
}) {
  const { t } = useI18n();
  const cardBoxRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<SquareCardObj | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; kind: MsgKind }>({
    text: "",
    kind: "info",
  });

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setPhase("loading");
    setMsg({ text: t("driver.co.loading"), kind: "info" });
    (async () => {
      try {
        const cfg = await getPaymentsConfig();
        if (!cfg.application_id || !cfg.location_id) {
          if (alive) {
            setPhase("degraded");
            setMsg({ text: t("driver.co.notReady"), kind: "info" });
          }
          return;
        }
        await loadSquareSdk(cfg.env);
        const Square = (window as unknown as { Square: SquarePayments }).Square;
        const payments = await Square.payments(cfg.application_id, cfg.location_id);
        const card = await payments.card();
        if (!alive || !cardBoxRef.current) return;
        await card.attach(cardBoxRef.current);
        cardRef.current = card;
        setPhase("ready");
        setMsg({ text: t("driver.co.secure"), kind: "info" });
      } catch {
        if (alive) setMsg({ text: t("driver.err.sdk"), kind: "err" });
      }
    })();
    return () => {
      alive = false;
    };
    // Re-mount the card each time the modal opens.
  }, [open, t]);

  const errorText = (code: string): string =>
    KNOWN_ERRORS.has(code) ? t(`driver.err.${code}`) : t("driver.err.generic");

  const pay = async () => {
    const e = email.trim();
    if (!e || !e.includes("@") || !e.split("@")[1]?.includes(".")) {
      setMsg({ text: t("driver.co.invalidEmail"), kind: "err" });
      return;
    }
    if (!cardRef.current) {
      setMsg({ text: t("driver.err.sdk"), kind: "err" });
      return;
    }
    setBusy(true);
    setMsg({ text: t("driver.co.processing"), kind: "info" });
    try {
      const result = await cardRef.current.tokenize();
      if (result.status !== "OK" || !result.token) {
        setMsg({ text: t("driver.err.card_invalid"), kind: "err" });
        setBusy(false);
        return;
      }
      await subscribe({ plan_key: planKey, source_id: result.token, email: e });
      setPhase("done");
      setMsg({ text: t("driver.co.success"), kind: "ok" });
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      setMsg({ text: errorText(code), kind: "err" });
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="bv-ov on" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bv-modal">
        <span className="bv-closex" onClick={onClose} role="button" aria-label="close">
          &times;
        </span>
        <h3>{t("driver.co.title")}</h3>
        <div className="bv-mt">
          {priceLabel} · {t("driver.co.sub")}
        </div>

        <label htmlFor="bv-co-email">{t("driver.co.emailLabel")}</label>
        <input
          id="bv-co-email"
          type="email"
          autoComplete="email"
          placeholder={t("driver.co.emailPh")}
          value={email}
          onChange={(ev) => setEmail(ev.target.value)}
        />

        <label>{t("driver.co.cardLabel")}</label>
        <div ref={cardBoxRef} className="bv-cardbox" style={{ display: phase === "degraded" ? "none" : "block" }} />

        <div className={`bv-msg ${msg.kind}`}>{msg.text}</div>

        {phase === "degraded" ? (
          <a
            className="bv-btn cyan block"
            href={`mailto:${salesEmail}?subject=Operator%20-%20Black%20Volt`}
          >
            {t("driver.co.contactUs")}
          </a>
        ) : (
          <button
            className="bv-btn cyan block"
            disabled={busy || phase === "done" || phase === "loading"}
            onClick={pay}
          >
            {phase === "done"
              ? t("driver.co.activeBtn")
              : busy
                ? t("driver.co.processing")
                : `${t("driver.co.payBtn")} · ${priceLabel}`}
          </button>
        )}
        <div className="bv-foot">{t("driver.co.foot")}</div>
      </div>
    </div>
  );
}
