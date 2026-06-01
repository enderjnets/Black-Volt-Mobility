"use client";

/* Square Web Payments SDK card form. Loads the SDK from the sandbox or production
   CDN (per the `env` prop), mounts a card input, and tokenizes on pay → hands the
   token (nonce) to onToken. Card data never touches our backend. The caller
   (Booking) owns the payments-config fetch and only renders this when Square is
   configured. */

import { useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { useI18n } from "@/lib/i18n";

let sdkPromise: Promise<void> | null = null;
function loadSdk(env: string): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("ssr"));
  if ((window as unknown as { Square?: unknown }).Square) return Promise.resolve();
  if (sdkPromise) return sdkPromise;
  const src =
    env === "production"
      ? "https://web.squarecdn.com/v1/square.js"
      : "https://sandbox.web.squarecdn.com/v1/square.js";
  sdkPromise = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("square_sdk_load_failed"));
    document.head.appendChild(s);
  });
  return sdkPromise;
}

type SquareCardObj = {
  attach: (el: HTMLElement) => Promise<void>;
  tokenize: () => Promise<{ status: string; token?: string }>;
};

export function SquareCard({
  applicationId,
  locationId,
  env,
  amountLabel,
  sandbox,
  onToken,
}: {
  applicationId: string;
  locationId: string;
  env: string;
  amountLabel: string;
  sandbox?: boolean;
  onToken: (token: string) => void | Promise<void>;
}) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<SquareCardObj | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await loadSdk(env);
        const Square = (
          window as unknown as {
            Square: { payments: (a: string, l: string) => Promise<{ card: () => Promise<SquareCardObj> }> };
          }
        ).Square;
        const payments = await Square.payments(applicationId, locationId);
        const card = await payments.card();
        if (!alive || !containerRef.current) return;
        await card.attach(containerRef.current);
        cardRef.current = card;
        setReady(true);
      } catch {
        if (alive) setErr("sdk_error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [applicationId, locationId, env]);

  const pay = async () => {
    if (!cardRef.current || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const result = await cardRef.current.tokenize();
      if (result.status === "OK" && result.token) {
        await onToken(result.token);
      } else {
        setErr("card_invalid");
      }
    } catch {
      setErr("card_invalid");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div
        ref={containerRef}
        style={{
          minHeight: 52,
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: "4px 8px",
        }}
      />
      {err && (
        <div style={{ fontSize: 12.5, color: "var(--danger)", display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="alert-circle" size={14} color="var(--danger)" />
          {t(`pay.err.${err}`)}
        </div>
      )}
      <Button variant="solid" full size="lg" icon="zap" disabled={!ready || busy} onClick={pay}>
        {busy ? t("pay.processing") : `${t("book.paybtn")} · ${amountLabel}`}
      </Button>
      {sandbox && (
        <div style={{ fontSize: 11, color: "var(--fg3)", textAlign: "center" }}>{t("pay.sandbox")}</div>
      )}
    </div>
  );
}
