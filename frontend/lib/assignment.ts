/* Client helpers for handing a ride to another driver on the team: who can take it,
   the money split, and marking what was already paid out. Same-origin `/api` with the
   session cookie, mirroring lib/rideMessages.ts. */
import { ApiError, fmtApiDetail } from "./booking";

export interface AssignableDriver {
  email: string;
  name: string;
}

// Every amount in dollars. `owner_amount`/`gross` are omitted for the assigned driver:
// they only ever see their own cut.
export interface EarningsSplit {
  gross?: number;
  square_fee?: number;
  tax_reserve?: number;
  net?: number;
  // Gratuity: goes to the driver whole, on top of their share. Never split, no fee.
  tip?: number;
  driver_amount: number;
  owner_amount?: number;
  driver_share_pct: number;
  payout_status?: "unpaid" | "paid";
  paid_at?: string | null;
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api/v1${url}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(
      fmtApiDetail((d as { detail?: unknown }).detail, `${method}:${r.status}`),
      r.status,
    );
  }
  return r.json();
}

export async function listAssignableDrivers(): Promise<AssignableDriver[]> {
  const r = await fetch("/api/v1/rides/assignable-drivers", {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new ApiError(`drivers:${r.status}`, r.status);
  return r.json();
}

export async function assignRide(
  rideId: number,
  driverEmail: string,
  driverSharePct: number,
  note?: string,
): Promise<Record<string, unknown>> {
  return send(`/rides/${rideId}/assign`, "POST", {
    driver_email: driverEmail,
    driver_share_pct: driverSharePct,
    note: note || undefined,
  });
}

export async function unassignRide(rideId: number): Promise<Record<string, unknown>> {
  return send(`/rides/${rideId}/assign`, "DELETE");
}

export async function updatePayout(
  rideId: number,
  patch: { driver_share_pct?: number; paid?: boolean },
): Promise<Record<string, unknown>> {
  return send(`/rides/${rideId}/payout`, "PATCH", patch);
}

// What the split WOULD be at this share, before saving anything.
export async function previewEarnings(
  rideId: number,
  driverSharePct: number,
): Promise<EarningsSplit> {
  const r = await fetch(
    `/api/v1/rides/${rideId}/earnings-preview?driver_share_pct=${driverSharePct}`,
    { credentials: "include", cache: "no-store" },
  );
  if (!r.ok) throw new ApiError(`preview:${r.status}`, r.status);
  return r.json();
}
