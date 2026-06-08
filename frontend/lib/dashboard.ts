/* Client helpers for the driver dashboard read-models (stats + clients). */

export interface DashStats {
  today: { rides: number; revenue: number; upcoming: number };
  next_pickup: { at: string | null; client: string | null; pickup: string | null } | null;
  totals: { clients: number; rides: number; completed: number };
  week: { day: string; date: string; rides: number }[];
}

export interface ClientRow {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
  lang: string;
  home_address: string | null;
  rides_count: number;
  lifetime_spend: number;
  tier: "VIP" | "Regular" | "New";
  last_ride_at: string | null;
  created_at: string | null;
}

import type { RideRow } from "./booking";
import { fmtApiDetail } from "./booking";

export interface ClientDetail extends ClientRow {
  rides: RideRow[];
}

/* Default drop-off for a brand-new client with no history — Black Volt's home
   airport (DEN). Used as the fallback "airport" when nothing else is known. */
export const DEN_AIRPORT_ADDR =
  "Denver International Airport (DEN), 8500 Peña Blvd, Denver, CO 80249";

const AIRPORT_RE = /\b(airport|aeropuerto|international|intl|den|dia|terminal|pe[ñn]a)\b/i;

export function isAirportLike(addr: string): boolean {
  return AIRPORT_RE.test(addr || "");
}

/* Most frequently used address (original casing) matching `predicate`; ties
   broken by first appearance. Null when no address qualifies. */
function topAddress(addrs: string[], predicate: (a: string) => boolean): string | null {
  const seen = new Map<string, { count: number; label: string; order: number }>();
  let order = 0;
  for (const raw of addrs) {
    const label = (raw || "").trim();
    if (!label || !predicate(label)) continue;
    const key = label.toLowerCase();
    const e = seen.get(key);
    if (e) e.count += 1;
    else seen.set(key, { count: 1, label, order: order++ });
  }
  let best: { count: number; label: string; order: number } | null = null;
  for (const e of seen.values()) {
    if (!best || e.count > best.count || (e.count === best.count && e.order < best.order)) best = e;
  }
  return best ? best.label : null;
}

export interface PrefillRoute {
  home: string;
  airport: string;
}

/* Best-guess pickup (home) + drop-off (airport) for a client, used to prefill
   the Add-ride form. Hybrid: a saved `home_address` wins; otherwise infer the
   home from the most frequent non-airport address in the ride history. The
   airport is the most frequent airport-like address, else DEN by default. */
export function inferRoute(detail: ClientDetail): PrefillRoute {
  const addrs: string[] = [];
  for (const r of detail.rides || []) {
    if (r.pickup) addrs.push(r.pickup);
    if (r.dropoff) addrs.push(r.dropoff);
  }
  const savedHome = (detail.home_address || "").trim();
  const home = savedHome || topAddress(addrs, (a) => !isAirportLike(a)) || "";
  const airport = topAddress(addrs, (a) => isAirportLike(a)) || DEN_AIRPORT_ADDR;
  return { home, airport };
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
  return r.json();
}

export async function getDashboardStats(): Promise<DashStats> {
  return jget<DashStats>("/v1/dashboard/stats");
}

export async function listClients(): Promise<ClientRow[]> {
  const r = await jget<{ clients: ClientRow[] }>("/v1/clients");
  return r.clients;
}

export async function getClientDetail(id: number): Promise<ClientDetail> {
  return jget<ClientDetail>(`/v1/clients/${id}`);
}

/* Compact client match for the Add-ride name autocomplete. */
export interface ClientLite {
  id: number;
  name: string;
  phone: string | null;
  lang: string;
}

export async function searchClients(q: string): Promise<ClientLite[]> {
  const r = await jget<{ clients: ClientLite[] }>(
    `/v1/clients/search?q=${encodeURIComponent(q)}`,
  );
  return r.clients;
}

export async function createClient(body: {
  name: string;
  phone?: string | null;
  email?: string | null;
  lang?: string;
  home_address?: string | null;
}): Promise<ClientDetail> {
  const r = await fetch("/api/v1/clients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `client:${r.status}`));
  }
  return r.json();
}

export async function deleteClient(id: number): Promise<void> {
  const r = await fetch(`/api/v1/clients/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `client:${r.status}`));
  }
}

export async function updateClient(
  id: number,
  body: {
    name?: string;
    phone?: string | null;
    email?: string | null;
    lang?: string;
    home_address?: string | null;
  },
): Promise<ClientDetail> {
  const r = await fetch(`/api/v1/clients/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `client:${r.status}`));
  }
  return r.json();
}
