/* Admin access-list (Team) API — super-admin only. Backs the Team panel. */

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
