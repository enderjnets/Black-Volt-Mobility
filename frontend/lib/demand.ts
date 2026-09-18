/* Client for the "Where to wait" API (one-tap log, Uber export import, week planner). */
import { ApiError, fmtApiDetail } from "./booking";

export type LogKind = "online" | "here" | "ping" | "offer" | "offline";
export type Product = "black_suv" | "black" | "comfort" | "x" | "xl";
export const PRODUCTS: Product[] = ["black_suv", "black", "comfort", "x", "xl"];
export const DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export interface LogEvent {
  id: number;
  kind: LogKind;
  at: string;
  lat: number | null;
  lng: number | null;
  h3_r8: string | null;
  product: Product | null;
  accepted: boolean | null;
  fare: number | null;
  zone_key: string | null;
  no_position: boolean;
}

export interface TodayLog {
  state: "open" | "enroute" | "offline";
  open_since: string | null;
  events: LogEvent[];
  segments: { state: string; begin_at: string; end_at: string | null; minutes: number; zone_key: string | null }[];
}

export interface GpsSummary {
  start: string;
  end: string;
  days: number;
  pings: number;
  segments: { open: number; enroute: number; ontrip: number };
  trips_located: number;
  home_hours: number;
  top_waits: {
    h3_r8: string;
    hours: number;
    premium_requests: number;
    per_hour: number;
    place: string | null;
    distance_km: number | null;
    zone_key: string | null;
    zone_name: string | null;
    outside: boolean;
  }[];
}

export interface ImportSummary {
  files_found: string[];
  files_missing: { kind: string; consequence: string }[];
  skipped_rows: number;
  trips: { inserted: number; skipped: number; date_min: string | null; date_max: string | null; by_product: Record<string, number> };
  segments: { inserted: number; skipped: number };
  windows: { inserted: number; skipped: number };
  gps?: GpsSummary | null;
}

export interface WeekCell {
  mean: number;
  lo: number;
  hi: number;
  p15: number;
  own_share: number;
  reasons: { flights?: number; events?: string[]; holiday?: string | null; own_minutes?: number; own_offers?: number };
}

/* Where to physically park during a block. `source` is not decoration: it is the
   difference between "you have waited here and it paid" and "the census says this is
   the richest corner", and the driver deciding whether to drive there needs it. */
export interface WaitingSpot {
  lat: number;
  lng: number;
  source: "event" | "den_lot" | "your_data" | "income";
  place: string | null;
  near: string[];
  venue: string | null;
}

export interface TopBlock {
  dow: number;
  start_hour: number;
  end_hour: number;
  expected_offers: number;
  mean: number;
  reasons: WeekCell["reasons"];
  spot?: WaitingSpot | null;
  /* How many times a normal hour this block is. Both sides of the ratio come from
     the model: its scale is unverified, its ordering is not. */
  lift?: number | null;
}

export interface WeekPayload {
  zone: string | null;
  zone_name: string | null;
  zones: { key: string; name: string }[];
  computed_at: string | null;
  grid: WeekCell[][];
  top_blocks: TopBlock[];
  private_rides: { id: number; at: string; pickup: string }[];
  own_minutes_total: number;
  baseline_mean: number;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`), r.status);
  }
  return r.json();
}

async function jpost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`), r.status);
  }
  return r.json();
}

export function newEventId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function logEvent(body: {
  client_event_id: string;
  kind: LogKind;
  lat?: number | null;
  lng?: number | null;
  product?: Product;
  accepted?: boolean;
  fare?: number | null;
}): Promise<LogEvent> {
  return jpost<LogEvent>("/v1/demand/log", body);
}

export function getToday(): Promise<TodayLog> {
  return jget<TodayLog>("/v1/demand/log/today");
}

export function getImportStatus(): Promise<(ImportSummary & { at: string }) | { never: true }> {
  return jget("/v1/demand/import/status");
}

export function getWeek(zone?: string | null): Promise<WeekPayload> {
  const q = zone ? `?zone=${encodeURIComponent(zone)}` : "";
  return jget<WeekPayload>(`/v1/demand/week${q}`);
}

/* XHR so the upload can report progress; fetch cannot. */
export function importZip(file: File, onProgress?: (pct: number) => void): Promise<ImportSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/demand/import");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let body: unknown = {};
      try {
        body = JSON.parse(xhr.responseText || "{}");
      } catch {
        body = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as ImportSummary);
      else
        reject(
          new ApiError(
            fmtApiDetail((body as { detail?: unknown }).detail, `import:${xhr.status}`),
            xhr.status,
          ),
        );
    };
    xhr.onerror = () => reject(new ApiError("import:network", 0));
    const fd = new FormData();
    fd.append("file", file, file.name);
    xhr.send(fd);
  });
}
