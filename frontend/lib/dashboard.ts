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
  rides_count: number;
  lifetime_spend: number;
  tier: "VIP" | "Regular" | "New";
  last_ride_at: string | null;
  created_at: string | null;
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
