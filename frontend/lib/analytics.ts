/* First-party usage tracker. Pseudonymous: a random visitor id in localStorage
   + a per-tab session id; no PII beyond what the session cookie already carries
   (added server-side). Events are batched and sent to /api/v1/track via
   sendBeacon (fallback fetch keepalive). Safe to import in SSR — every browser
   API is guarded. */

const VID_KEY = "bv_vid";
const SID_KEY = "bv_sid";
const FLUSH_MS = 4000;

type Ev = Record<string, unknown>;

let queue: Ev[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let device: string | null = null;
let utm: { source?: string; medium?: string; campaign?: string } | null = null;
let referrerSent = false;

function uuid(): string {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch {
    /* fall through */
  }
  return "v-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function visitorId(): string {
  if (typeof window === "undefined") return "";
  let v = localStorage.getItem(VID_KEY);
  if (!v) {
    v = uuid();
    localStorage.setItem(VID_KEY, v);
  }
  return v;
}

function sessionId(): string {
  if (typeof window === "undefined") return "";
  let s = sessionStorage.getItem(SID_KEY);
  if (!s) {
    s = uuid();
    sessionStorage.setItem(SID_KEY, s);
  }
  return s;
}

function deviceClass(): string {
  if (device) return device;
  if (typeof window === "undefined") return "desktop";
  const ua = navigator.userAgent.toLowerCase();
  const w = window.innerWidth;
  if (/ipad|tablet/.test(ua) || (/android/.test(ua) && !/mobi/.test(ua))) device = "tablet";
  else if (/mobi|iphone|android/.test(ua) || w < 600) device = "mobile";
  else device = "desktop";
  return device;
}

function parseUtm() {
  if (utm || typeof window === "undefined") return;
  const p = new URLSearchParams(window.location.search);
  utm = {
    source: p.get("utm_source") || undefined,
    medium: p.get("utm_medium") || undefined,
    campaign: p.get("utm_campaign") || undefined,
  };
}

function enqueue(ev: Ev) {
  if (typeof window === "undefined") return;
  queue.push({
    ...ev,
    visitor_id: visitorId(),
    session_id: sessionId(),
    device: deviceClass(),
    path: ev.path ?? window.location.pathname,
    ts: Date.now(),
  });
  if (!flushTimer) flushTimer = setTimeout(() => flush(), FLUSH_MS);
}

export function flush(useBeacon = false) {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (typeof window === "undefined" || queue.length === 0) return;
  const body = JSON.stringify({ events: queue });
  queue = [];
  try {
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon("/api/v1/track", new Blob([body], { type: "text/plain" }));
      return;
    }
  } catch {
    /* fall through to fetch */
  }
  fetch("/api/v1/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body,
    keepalive: true,
  }).catch(() => {});
}

export function track(type: string, props?: Record<string, unknown>) {
  enqueue({ type, props });
}

export function trackSessionStart() {
  parseUtm();
  enqueue({
    type: "session_start",
    referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
    utm_source: utm?.source,
    utm_medium: utm?.medium,
    utm_campaign: utm?.campaign,
  });
}

export function trackPageview(path: string) {
  parseUtm();
  const ev: Ev = { type: "pageview", path };
  if (!referrerSent) {
    referrerSent = true;
    if (typeof document !== "undefined" && document.referrer) ev.referrer = document.referrer;
  }
  enqueue(ev);
}

export function trackDuration(path: string, ms: number) {
  if (!ms || ms <= 0) return;
  enqueue({ type: "page_duration", path, duration_ms: Math.round(ms) });
}

/* ─── Insights dashboard (read side) ─────────────────────────────────────── */

export interface CountRow {
  value: string;
  count: number;
}
export interface AnalyticsSummary {
  days: number;
  totals: { visitors: number; sessions: number; pageviews: number; avg_session_ms: number };
  timeseries: { day: string; pageviews: number; visitors: number }[];
  top_pages: { path: string; views: number; avg_ms: number }[];
  funnel: Record<string, number>;
  devices: CountRow[];
  countries: CountRow[];
  referrers: CountRow[];
  utm_sources: CountRow[];
  recent: { type: string; path: string | null; created_at: string }[];
}

export async function getAnalyticsSummary(days = 30): Promise<AnalyticsSummary> {
  const r = await fetch(`/api/v1/analytics/summary?days=${days}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`summary:${r.status}`);
  return r.json();
}
