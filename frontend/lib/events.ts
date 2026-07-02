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
}

export interface PublicEvent {
  slug: string;
  title: string;
  performer: string | null;
  venue_name: string;
  starts_at: string;
  hero_url: string | null;
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

// ── public ───────────────────────────────────────────────────────────────────
export async function listPublicEvents(): Promise<PublicEvent[]> {
  return jget<PublicEvent[]>("/v1/events/public");
}
