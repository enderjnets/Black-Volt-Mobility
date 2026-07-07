/* Client helpers for the Black Volt booking API (same-origin /api → backend). */
import type { RidePreferences } from "./profile";

export interface QuoteLine {
  label: string;
  amount: number;
  qty?: number;
  multiplier?: number;
  pct?: number;
}

export interface Quote {
  currency: string;
  total: number;
  distance_miles: number;
  duration_minutes: number;
  is_airport: boolean;
  zone?: string | null;
  zone_name?: string | null;
  is_peak: boolean;
  is_loyalty: boolean;
  lines: QuoteLine[];
  route_simulated?: boolean;
  // Round-trip / event pricing (present when round_trip is requested).
  round_trip?: boolean;
  wait_fee?: number;
  event?: { slug: string; title: string } | null;
  return_at?: string | null;
}

export interface RateConfig {
  currency: string;
  minimum: number;
  base: number;
  per_mile: number;
  per_minute: number;
  airport_flat: number;
  extra_stop_fee: number;
  group_surcharge: number;
  group_threshold: number;
  peak_enabled: boolean;
  peak_multiplier: number;
  loyalty_discount_pct: number;
  zone_prices: Record<string, number>;
  zones: { key: string; name: string; default_flat: number }[];
}

export interface RideInput {
  pickup: string;
  dropoff: string;
  stops?: string[];
  pax?: number | null;
  scheduled_at?: string | null;
  flight_number?: string | null;
  lang?: string | null;
  notes?: string | null;
  passenger_name?: string | null;
  passenger_phone?: string | null;
  client_id?: number | null;
  fare_override?: number | null;
  ride_preferences?: RidePreferences | null;
  discount_code?: string;
  confirm?: boolean;
  round_trip?: boolean;
  return_at?: string | null;
  // Rider accepted the event reservation terms → deposit booking (1/3 now, balance day-of).
  terms_accepted?: boolean;
}

// Error carrying the HTTP status so callers can branch on it (e.g. a 401 from
// the quote endpoint triggers the sign-in wall) without parsing the message.
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new ApiError(`${path}:${r.status}`, r.status);
  return r.json();
}

// Normalize a FastAPI error body to a readable string. `detail` may be a string
// or a 422 array of {loc,msg} — never return the raw object (rendering it as a
// React child crashes the page; see the 422-render note in memory).
export function fmtApiDetail(d: unknown, fallback: string): string {
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    const parts = d
      .map((e) => {
        if (e && typeof e === "object") {
          const loc = Array.isArray((e as { loc?: unknown[] }).loc)
            ? String((e as { loc: unknown[] }).loc.at(-1))
            : "";
          const msg = (e as { msg?: string }).msg || "";
          return [loc, msg].filter(Boolean).join(": ");
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

async function jsend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(
      fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`),
      r.status,
    );
  }
  return r.json();
}

export async function getQuote(input: {
  pickup: string;
  dropoff: string;
  stops?: string[];
  pax?: number | null;
  scheduled_at?: string | null;
  is_loyalty?: boolean;
  is_peak?: boolean | null;
  discount_code?: string;
  round_trip?: boolean;
  return_at?: string | null;
}): Promise<Quote> {
  return jsend<Quote>("/v1/quote", "POST", input);
}

export async function validateDiscount(
  code: string,
): Promise<{ valid: boolean; discount_pct: number }> {
  return jsend<{ valid: boolean; discount_pct: number }>(
    "/v1/discounts/validate",
    "POST",
    { code },
  );
}

export async function placesAutocomplete(
  q: string,
): Promise<{ description: string; place_id: string | null }[]> {
  const r = await jget<{ suggestions: { description: string; place_id: string | null }[] }>(
    `/v1/places/autocomplete?q=${encodeURIComponent(q)}`,
  );
  return r.suggestions;
}

export async function getRateConfig(): Promise<RateConfig> {
  return jget<RateConfig>("/v1/rate-config");
}

export async function updateRateConfig(changes: Partial<RateConfig>): Promise<RateConfig> {
  return jsend<RateConfig>("/v1/rate-config", "PUT", changes);
}

export async function createRide(input: RideInput): Promise<{ id: number; fare_total: number }> {
  return jsend("/v1/rides", "POST", input);
}

// Confirm a QUOTED ride the rider chose to pay on completion (cash / pay the
// driver at drop-off). No online charge — moves the ride to CONFIRMED and onto
// the driver's calendar. Idempotent.
export async function confirmRide(rideId: number): Promise<RideRow> {
  return jsend<RideRow>(`/v1/rides/${rideId}/confirm`, "POST");
}

// Cancel a ride the rider no longer needs. Allowed before the driver is en
// route. Refund is automatic when cancelling 24h+ ahead; cancelling within 24h
// may leave a cancellation fee to the driver's discretion.
export async function cancelRide(rideId: number): Promise<RideRow> {
  return jsend<RideRow>(`/v1/rides/${rideId}/cancel`, "POST");
}

// Driver contact attached to a ride once a driver is assigned — lets the rider
// call/text their driver from /trips.
export interface AssignedDriver {
  name: string | null;
  phone: string | null;
  vehicle: string | null;
  rating: number | null;
}

export interface RideRow {
  id: number;
  status: string;
  passenger_name: string | null;
  client_name?: string | null;
  client_phone?: string | null;
  pickup: string;
  dropoff: string;
  scheduled_at: string | null;
  fare_total: number | null;
  currency?: string;
  pax?: number | null;
  flight_number: string | null;
  payment_method?: string;
  paid?: boolean;
  paid_at?: string | null;
  overdue?: boolean;
  assigned_driver?: AssignedDriver;
}

export type PaymentMethod = "cash" | "square" | "venmo" | "zelle" | "other";

export async function listRides(status?: string): Promise<RideRow[]> {
  const r = await jget<{ rides: RideRow[] }>(`/v1/rides${status ? `?status=${status}` : ""}`);
  return r.rides;
}

export interface RideDetail extends RideRow {
  stops: { text: string }[] | null;
  distance_miles: number | null;
  duration_minutes: number | null;
  price_breakdown: Quote | null;
  // Event deposit reservation: 1/3 charged, balance collected in person (cents). Null otherwise.
  deposit_cents: number | null;
  balance_due_cents: number | null;
  lang: string | null;
  notes: string | null;
  google_event_id: string | null;
  created_at: string | null;
  client: {
    id: number;
    name: string | null;
    phone: string | null;
    email: string | null;
    preferences?: RidePreferences;
  } | null;
  // Per-ride preferences chosen at booking (snapshot). Null falls back to the
  // client's standing preferences for display.
  ride_preferences: RidePreferences | null;
  cancelled_at: string | null;
  cancellation_fee_eligible: boolean;
  payment: {
    id: number;
    status: string;
    amount: number;
    currency: string;
    simulated: boolean;
  } | null;
}

export async function getRideDetail(id: number): Promise<RideDetail> {
  return jget<RideDetail>(`/v1/rides/${id}`);
}

// Fields a driver can change on an existing ride (status/payment + change of plans).
export interface RideEdit {
  status?: string;
  payment_method?: PaymentMethod;
  paid?: boolean;
  pickup?: string;
  dropoff?: string;
  scheduled_at?: string | null;
  pax?: number | null;
  flight_number?: string | null;
  notes?: string | null;
  lang?: string | null;
  fare_override?: number | null;
}

export async function updateRide(id: number, body: RideEdit): Promise<RideRow> {
  return jsend<RideRow>(`/v1/rides/${id}`, "PATCH", body);
}

// Permanently remove a cancelled/no-show ride (204, no body). The backend
// rejects non-cancelled rides with 409.
export async function deleteRide(id: number): Promise<void> {
  const r = await fetch(`/api/v1/rides/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(
      fmtApiDetail((d as { detail?: unknown }).detail, `ride:${r.status}`),
      r.status,
    );
  }
}

export interface RideUpdatePreview {
  current: Record<string, unknown>;
  proposed: {
    pickup: string;
    dropoff: string;
    scheduled_at: string | null;
    pax: number | null;
    flight_number: string | null;
    notes: string | null;
    lang: string | null;
    fare_total: number | null;
    distance_miles: number | null;
    duration_minutes: number | null;
  };
  conflicts: {
    id: number;
    name: string;
    scheduled_at: string;
    pickup: string;
    dropoff: string;
  }[];
}

export async function previewRideUpdate(id: number, changes: RideEdit): Promise<RideUpdatePreview> {
  return jsend<RideUpdatePreview>(`/v1/rides/${id}/preview-update`, "POST", changes);
}
