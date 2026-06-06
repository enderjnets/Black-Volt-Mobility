/* Maps backend ride statuses to the dashboard UI buckets + adapts API rides to
   the UI Ride shape used by RideRow. */

import { type RideRow } from "@/lib/booking";
import { type Ride, type RideUiStatus } from "./data";

export function uiStatus(backend: string): RideUiStatus {
  if (backend === "en_route") return "active";
  if (backend === "completed") return "done";
  if (backend === "cancelled" || backend === "no_show") return "cancelled";
  return "upcoming"; // requested / quoted / confirmed / assigned
}

// Filter bucket → backend statuses (for the Rides list filter).
export const BUCKET_STATUSES: Record<string, string[]> = {
  upcoming: ["requested", "quoted", "confirmed", "assigned"],
  active: ["en_route"],
  done: ["completed"],
  cancelled: ["cancelled", "no_show"],
};

/** Format an ISO datetime as "Today · 14:20" / "Jun 4 · 14:20" / "—". */
export function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  const isTomorrow = d.toDateString() === tomorrow.toDateString();
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  if (sameDay) return `Today · ${time}`;
  if (isTomorrow) return `Tomorrow · ${time}`;
  const day = d.toLocaleDateString([], { month: "short", day: "numeric" });
  return `${day} · ${time}`;
}

export function apiToUiRide(r: RideRow): Ride {
  return {
    id: `BV-${r.id}`,
    rid: r.id,
    client: r.client_name || r.passenger_name || "Guest",
    from: r.pickup,
    to: r.dropoff,
    time: fmtWhen(r.scheduled_at) === "—" ? "Not scheduled" : fmtWhen(r.scheduled_at),
    fare: Math.round(r.fare_total || 0),
    status: uiStatus(r.status),
    overdue: r.overdue,
    flight: r.flight_number || null,
  };
}

export function isToday(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return !isNaN(d.getTime()) && d.toDateString() === new Date().toDateString();
}
