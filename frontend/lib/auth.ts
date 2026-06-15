/* Client helpers for the Black Volt auth API (same-origin /api → backend). */

export interface Me {
  authenticated: boolean;
  auth_enabled: boolean;
  google_signin_enabled: boolean;
  google_client_id: string | null;
  role?: "owner" | "driver" | "passenger";
  email?: string | null;
  client_id?: number | null;
  tenant_id?: number | null;
  tenant_slug?: string | null;
  is_admin?: boolean;
}

async function jpost(path: string, body?: unknown): Promise<Response> {
  return fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function fetchMe(): Promise<Me> {
  const r = await fetch("/api/v1/auth/me", { credentials: "include", cache: "no-store" });
  if (!r.ok) {
    return { authenticated: false, auth_enabled: false, google_signin_enabled: false, google_client_id: null };
  }
  return r.json();
}

export async function loginPassword(password: string): Promise<{ ok: boolean; error?: string }> {
  const r = await jpost("/v1/auth/login", { password });
  if (r.ok) return { ok: true };
  const d = await r.json().catch(() => ({}));
  return { ok: false, error: d.detail || "login_failed" };
}

export async function loginGoogle(
  idToken: string,
  ref?: string | null,
): Promise<{ ok: boolean; error?: string }> {
  const r = await jpost("/v1/auth/login/google", { id_token: idToken, ref: ref || null });
  if (r.ok) return { ok: true };
  const d = await r.json().catch(() => ({}));
  return { ok: false, error: d.detail || "google_login_failed" };
}

export async function logout(): Promise<void> {
  await jpost("/v1/auth/logout");
}
