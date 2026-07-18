/* Client helpers for the dashboard notifications API (same-origin /api → backend). */
import { ApiError, fmtApiDetail } from "./booking";

export type NotificationKind =
  | "ride_new"
  | "ride_cancelled"
  | "chat_escalated"
  | "chat_message"
  | "ride_message"
  | "review_new"
  | "discount_redeemed"
  | "subscription_payment_failed";

export interface NotificationItem {
  id: number;
  kind: NotificationKind;
  data: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface NotificationsResult {
  unread: number;
  items: NotificationItem[];
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

export function listNotifications(): Promise<NotificationsResult> {
  return jget<NotificationsResult>("/v1/notifications");
}

export function markNotificationRead(id: number): Promise<{ ok: boolean }> {
  return jsend<{ ok: boolean }>(`/v1/notifications/${id}/read`, "POST");
}

export function markAllNotificationsRead(): Promise<{ ok: boolean }> {
  return jsend<{ ok: boolean }>("/v1/notifications/read-all", "POST");
}
