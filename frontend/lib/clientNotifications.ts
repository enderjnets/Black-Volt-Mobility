/* Client helpers for the passenger notifications API (same-origin /api → backend).
   Mirrors ./notifications.ts (the staff bell) but hits the passenger endpoints. */
import { ApiError, fmtApiDetail } from "./booking";

export type ClientNotificationKind = "ride_message" | "refund_full" | "refund_partial";

export interface ClientNotificationItem {
  id: number;
  kind: ClientNotificationKind;
  data: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface ClientNotificationsResult {
  unread: number;
  items: ClientNotificationItem[];
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new ApiError(`${path}:${r.status}`, r.status);
  return r.json();
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
    throw new ApiError(fmtApiDetail(d, `${path}:${r.status}`), r.status);
  }
  return r.json();
}

export function listClientNotifications(): Promise<ClientNotificationsResult> {
  return jget<ClientNotificationsResult>("/v1/client/notifications");
}

export function markClientNotificationRead(id: number): Promise<{ ok: boolean }> {
  return jsend<{ ok: boolean }>(`/v1/client/notifications/${id}/read`, "POST");
}

export function markAllClientNotificationsRead(): Promise<{ ok: boolean }> {
  return jsend<{ ok: boolean }>("/v1/client/notifications/read-all", "POST");
}
