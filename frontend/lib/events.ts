/* Featured-events module API client. Owner-admin only for the admin calls;
   listPublicEvents is used by the public home section. */

import { fmtApiDetail } from "./booking";

export interface EventSuggestion {
  id: number;
  source: string;
  title: string;
  performer: string | null;
  venue_name: string;
  venue_key: string | null;
  venue_address: string | null;
  distance_mi: number | null;
  starts_at: string;
  score: number | null;
  image_url: string | null;
  event_url: string | null;
  status: string;
}

export interface AdminEvent {
  id: number;
  slug: string;
  title: string;
  performer: string | null;
  venue_key: string;
  venue_name: string;
  venue_address: string | null;
  starts_at: string;
  hero_url: string | null;
  about_text: string | null;
  tips_text: string | null;
  status: string;
  event_url: string | null;
  event_fee: number;
  night_fee: number;
  night_cutoff: string;
  wait_fee_per_hour: number;
  est_duration_hours: number;
  round_trip_price: number | null;
  pricing_research: ResearchResult | null;
}

export interface RtLine {
  label: string;
  amount: number;
  qty?: number;
}

export interface RoundTripPreview {
  currency: string;
  lines: RtLine[];
  formula_total: number;
  total: number;
  overridden: boolean;
  capped: boolean;
  uber_black: number | null;
}

export interface ResearchZone {
  key: string;
  name: string;
  affluence: number;
  our_one_way: number;
  our_round_trip: number;
  uber_black: number;
  uber_black_suv: number;
  uber_round_trip: number;
  method: string;
  distance_from_base_mi: number;
  margin_pct: number;
  score: number;
}

export interface ResearchResult {
  zones: ResearchZone[];
  recommendation: string;
  method: string;
  venue: string;
}

export interface PublicEvent {
  slug: string;
  title: string;
  performer: string | null;
  venue_name: string;
  starts_at: string;
  hero_url: string | null;
}

export interface PickupSuggestion {
  pickup_at: string;
  arrive_by: string;
  travel_minutes_out: number;
  return_pickup_at: string;
  drop_home_minutes: number | null;
  traffic_aware: boolean;
}

export interface ScanResult {
  fetched: number;
  kept: number;
  created: number;
  updated: number;
  pruned: number;
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
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`));
  }
  return r.json();
}

// ── admin ────────────────────────────────────────────────────────────────────
export async function listSuggestions(venueKey?: string): Promise<EventSuggestion[]> {
  const q = venueKey ? `?venue_key=${encodeURIComponent(venueKey)}` : "";
  return jget<EventSuggestion[]>(`/v1/events/suggestions${q}`);
}

export async function approveSuggestion(id: number): Promise<AdminEvent & { post_ids: number[] }> {
  return jsend(`/v1/events/suggestions/${id}/approve`, "POST");
}

export async function dismissSuggestion(id: number): Promise<{ ok: boolean }> {
  return jsend(`/v1/events/suggestions/${id}/dismiss`, "POST");
}

export async function scanNow(): Promise<ScanResult> {
  return jsend<ScanResult>("/v1/events/scan", "POST");
}

export async function listAdminEvents(): Promise<AdminEvent[]> {
  return jget<AdminEvent[]>("/v1/events/admin");
}

export async function patchEvent(id: number, patch: Partial<AdminEvent>): Promise<AdminEvent> {
  return jsend<AdminEvent>(`/v1/events/admin/${id}`, "PATCH", patch);
}

export async function generateEventPost(
  id: number,
  kind: "video" | "image",
): Promise<{ post_id: number; kind: string }> {
  return jsend(`/v1/events/admin/${id}/posts`, "POST", { kind });
}

export async function pricingPreview(id: number, origin?: string): Promise<RoundTripPreview> {
  const q = origin ? `?origin=${encodeURIComponent(origin)}` : "";
  return jget<RoundTripPreview>(`/v1/events/admin/${id}/pricing-preview${q}`);
}

export async function runResearch(id: number): Promise<ResearchResult> {
  return jsend<ResearchResult>(`/v1/events/admin/${id}/research`, "POST");
}

// ── public ───────────────────────────────────────────────────────────────────
export async function listPublicEvents(): Promise<PublicEvent[]> {
  return jget<PublicEvent[]>("/v1/events/public");
}

export async function getPickupSuggestion(
  slug: string,
  origin: string,
): Promise<PickupSuggestion> {
  return jget<PickupSuggestion>(
    `/v1/events/public/${encodeURIComponent(slug)}/pickup-suggestion` +
      `?origin=${encodeURIComponent(origin)}`,
  );
}
