/* Client helpers for the Square payments API. */

export interface PaymentsConfig {
  enabled: boolean;
  live: boolean;
  env: string;
  application_id: string | null;
  location_id: string | null;
}

export interface PaymentResult {
  id: number;
  ride_id: number | null;
  status: string;
  amount: number;
  currency: string;
  simulated: boolean;
}

export async function getPaymentsConfig(): Promise<PaymentsConfig> {
  const r = await fetch("/api/v1/payments/config", { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`payments_config:${r.status}`);
  return r.json();
}

export async function authorizePayment(input: {
  ride_id: number;
  source_id: string;
  amount?: number;
}): Promise<PaymentResult> {
  const r = await fetch("/api/v1/payments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(input),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : `payment:${r.status}`);
  }
  return r.json();
}

export async function capturePayment(paymentId: number): Promise<PaymentResult> {
  const r = await fetch(`/api/v1/payments/${paymentId}/capture`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : `capture:${r.status}`);
  }
  return r.json();
}

// Driver/staff decision on a cancelled ride's refund. feePct: 0 = full refund;
// 20/30 = cancellation fee the driver keeps (the rest is refunded). A fee is
// only accepted by the backend when the rider cancelled <24h before pickup.
export async function refundDecision(rideId: number, feePct: number): Promise<void> {
  const r = await fetch(`/api/v1/rides/${rideId}/refund-decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ fee_pct: feePct }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : `refund:${r.status}`);
  }
}
