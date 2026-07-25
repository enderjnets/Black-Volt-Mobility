/* Client helpers for per-ride passenger<->driver messages. Same-origin `/api`
   with the session cookie, mirroring lib/booking.ts. */
import { ApiError, fmtApiDetail } from "./booking";

export interface RideMessage {
  id: number;
  sender: "client" | "driver";
  body: string;
  created_at: string;
}

export interface RideMessagesResult {
  messages: RideMessage[];
  unread: number;
  chat_open: boolean;
}

export async function listRideMessages(
  rideId: number,
  afterId?: number,
): Promise<RideMessagesResult> {
  const q = afterId ? `?after_id=${afterId}` : "";
  const r = await fetch(`/api/v1/rides/${rideId}/messages${q}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new ApiError(`messages:${r.status}`, r.status);
  return r.json();
}

export async function sendRideMessage(rideId: number, body: string): Promise<RideMessage> {
  const r = await fetch(`/api/v1/rides/${rideId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ body }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(
      fmtApiDetail((d as { detail?: unknown }).detail, `send:${r.status}`),
      r.status,
    );
  }
  return r.json();
}

/* ── internal channel: ride owner <-> assigned driver ─────────────────────── */
export interface InternalMessage {
  id: number;
  body: string;
  mine: boolean;
  created_at: string;
  read_at?: string | null;
}

export interface InternalThread {
  messages: InternalMessage[];
  unread: number;
  can_write: boolean;
}

export async function listInternalMessages(rideId: number): Promise<InternalThread> {
  const r = await fetch(`/api/v1/rides/${rideId}/internal-messages`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new ApiError(`internal:${r.status}`, r.status);
  return r.json();
}

export async function sendInternalMessage(
  rideId: number,
  body: string,
): Promise<InternalMessage> {
  const r = await fetch(`/api/v1/rides/${rideId}/internal-messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ body }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(
      fmtApiDetail((d as { detail?: unknown }).detail, `send:${r.status}`),
      r.status,
    );
  }
  return r.json();
}
