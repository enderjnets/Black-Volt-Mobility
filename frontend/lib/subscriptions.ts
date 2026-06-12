/* Client helper for the PUBLIC driver subscription API. Posts the tokenized card
   (source_id) — never raw card data — to the backend, which talks to Square with
   the secret token server-side. Mirrors lib/payments.ts. */

import { fmtApiDetail } from "./booking";

export interface SubscribeInput {
  plan_key: string;
  source_id: string; // Square Web Payments SDK nonce
  email: string;
}

export interface SubscribeResult {
  status: string; // active | pending | past_due | canceled
  subscription_id: string | null;
  simulated: boolean;
}

export async function subscribe(input: SubscribeInput): Promise<SubscribeResult> {
  const r = await fetch("/api/v1/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(input),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    // The backend returns a stable public_code in `detail`; surface it so the UI
    // can map it to a localized message (falls back to a generic string).
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `subscribe:${r.status}`));
  }
  return r.json();
}
