/* Admin access-list (Team) API — super-admin only. Backs the Team panel. */

import type { RideRow } from "./booking";

export interface TeamMember {
  email: string;
  role: string;
  active: boolean;
  name: string | null;
  tenant_slug: string | null;
  immutable: boolean;
  created_at: string | null;
  last_login: string | null;
  rides: number;
  revenue: number;
  last_activity: string | null;
  email_status?: string | null;
}

function detailOf(d: unknown, fallback: string): string {
  if (typeof d === "string") return d;
  return fallback;
}

async function send(path: string, method: string, body?: unknown): Promise<Response> {
  return fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function listTeam(): Promise<TeamMember[]> {
  const r = await fetch("/api/v1/team", { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`team:${r.status}`);
  return r.json();
}

export async function addMember(email: string, name?: string, lang?: string): Promise<TeamMember> {
  const r = await send("/v1/team", "POST", { email, name: name || null, lang: lang || null });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `team:${r.status}`));
  }
  return r.json();
}

export async function setActive(email: string, active: boolean): Promise<TeamMember> {
  const r = await send(`/v1/team/${encodeURIComponent(email)}`, "PATCH", { active });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `team:${r.status}`));
  }
  return r.json();
}

export async function setRole(email: string, role: "admin" | "driver"): Promise<TeamMember> {
  const r = await send(`/v1/team/${encodeURIComponent(email)}`, "PATCH", { role });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `team:${r.status}`));
  }
  return r.json();
}

export async function resendInvite(email: string): Promise<string> {
  const r = await send(`/v1/team/${encodeURIComponent(email)}/resend-invite`, "POST");
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `team:${r.status}`));
  }
  return (await r.json()).email_status as string;
}

export async function removeMember(email: string): Promise<void> {
  const r = await send(`/v1/team/${encodeURIComponent(email)}`, "DELETE");
  if (!r.ok && r.status !== 204) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `team:${r.status}`));
  }
}

/* ---- Member detail (drawer) ---- */

export interface MemberSubscription {
  plan_key: string;
  status: string;
  current_period_end: string | null;
  simulated: boolean;
  paid: boolean;
}

export interface CountRow {
  value: string;
  count: number;
}

export interface MemberEngagement {
  visitors: number;
  sessions: number;
  pageviews: number;
  avg_session_ms: number;
  funnel: Record<string, number>;
  devices: CountRow[];
  countries: CountRow[];
}

export interface MemberActivity {
  type: string;
  path: string | null;
  created_at: string;
}

export interface TeamMemberDetail {
  email: string;
  name: string | null;
  role: string;
  active: boolean;
  immutable: boolean;
  provisioned: boolean;
  added_by: string | null;
  created_at: string | null;
  last_login: string | null;
  tenant_slug: string | null;
  tenant_name: string | null;
  tenant_created_at: string | null;
  subscription: MemberSubscription | null;
  rides: { total: number; completed: number; upcoming: number; cancelled: number };
  revenue_total: number;
  clients: number;
  first_ride_at: string | null;
  last_ride_at: string | null;
  week: { day: string; date: string; revenue: number }[];
  week_total: number;
  engagement: MemberEngagement | null;
  recent_rides: RideRow[];
  recent_activity: MemberActivity[];
}

export async function getTeamMemberDetail(email: string): Promise<TeamMemberDetail> {
  const r = await fetch(`/api/v1/team/${encodeURIComponent(email)}/detail`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`team-detail:${r.status}`);
  return r.json();
}
