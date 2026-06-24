/* Per-user Google Calendar connection (dashboard Settings → integrations). */

export interface CalendarConnection {
  connected: boolean;
  google_email: string | null;
  calendar_id: string | null;
  connected_at: string | null;
  // Admins use the shared Black Volt calendar — they don't connect their own.
  is_admin: boolean;
  // Whether the server has the OAuth client + encryption key configured.
  oauth_configured: boolean;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
  return r.json();
}

export async function getCalendarConnection(): Promise<CalendarConnection> {
  return jget<CalendarConnection>("/v1/calendar/connection");
}

/** Kick off the Google consent flow (full-page redirect to Google). */
export async function startCalendarConnect(): Promise<void> {
  const r = await fetch("/api/v1/calendar/connect", {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error((d as { detail?: string }).detail || `connect:${r.status}`);
  }
  const { auth_url } = (await r.json()) as { auth_url: string };
  window.location.href = auth_url;
}

export async function disconnectCalendar(): Promise<void> {
  const r = await fetch("/api/v1/calendar/disconnect", {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`disconnect:${r.status}`);
}
