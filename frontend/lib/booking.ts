/* Client helpers for the Black Volt booking API (same-origin /api → backend). */

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
  is_peak: boolean;
  is_loyalty: boolean;
  lines: QuoteLine[];
  route_simulated?: boolean;
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
  fare_override?: number | null;
  confirm?: boolean;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
  return r.json();
}

async function jsend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
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
}): Promise<Quote> {
  return jsend<Quote>("/v1/quote", "POST", input);
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
  lang: string | null;
  notes: string | null;
  google_event_id: string | null;
  created_at: string | null;
  client: { id: number; name: string | null; phone: string | null } | null;
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

export async function updateRide(
  id: number,
  body: { status?: string; payment_method?: PaymentMethod; paid?: boolean },
): Promise<RideRow> {
  return jsend<RideRow>(`/v1/rides/${id}`, "PATCH", body);
}
