/* Client for the Flights API (the driver's own flights, soonest first). */
import { ApiError } from "./booking";

export type FlightDirection = "arrival" | "departure";

/* Where the live status came from. "none" means there is no provider configured and the
   screen must say so — never fill the gap with a plausible-looking time. */
export type LiveSource = "none" | "simulated" | "aeroapi";

export interface UpcomingFlight {
  ride_id: number;
  /** "UA 1377", or the bare number when the airline is missing. */
  code: string;
  carrier: string | null;
  airline: string | null;
  number: number;
  needs_airline: boolean;
  /** Exactly what is stored on the ride, for the edit link. */
  raw: string;
  direction: FlightDirection;
  client: string | null;
  pickup: string;
  dropoff: string;
  scheduled_at: string;
  /** Pickup + the ride's duration: when the passenger reaches the terminal. Departures
      only, and never a "leave home" time — nothing here knows where the car is. */
  airport_eta: string | null;
  distance_miles: number | null;
  duration_minutes: number | null;
  status: string;
  sort_at: string;
  live: null;
}

export interface UpcomingFlights {
  generated_at: string;
  window_hours: number;
  live_source: LiveSource;
  flights: UpcomingFlight[];
  missing_airline: number;
  skipped: {
    no_scheduled_time: number;
    not_an_airport_ride: number;
    unreadable: number;
  };
}

export async function listUpcomingFlights(hours?: number): Promise<UpcomingFlights> {
  const qs = hours ? `?hours=${hours}` : "";
  const r = await fetch(`/api/v1/flights/upcoming${qs}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new ApiError(`flights:${r.status}`, r.status);
  return r.json();
}

/* The carriers worth offering when a stored flight number has no airline. Ordered by how
   often they appear in this driver's own history, so the first tap is usually the right
   one. "Otra" falls through to editing the ride. */
export const DEN_CARRIERS: { code: string; name: string }[] = [
  { code: "UA", name: "United Airlines" },
  { code: "WN", name: "Southwest Airlines" },
  { code: "DL", name: "Delta Air Lines" },
  { code: "AA", name: "American Airlines" },
  { code: "F9", name: "Frontier Airlines" },
  { code: "AS", name: "Alaska Airlines" },
  { code: "NK", name: "Spirit Airlines" },
  { code: "B6", name: "JetBlue" },
];
