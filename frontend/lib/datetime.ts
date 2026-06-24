// Shared date/time helpers for ride scheduling. Used by the dashboard Add Ride
// form, the public booking form, and the branded date/time picker so the parsing
// rules (and the v0.40.1 guarantee — never save a ride without a time) live in
// one place.

export const pad2 = (n: number) => String(n).padStart(2, "0");

// Normalize a free-text/AI date to YYYY-MM-DD (what the picker/native input need).
// Returns "" when it can't be parsed — better an empty picker than a silently
// wrong value. Handles ISO and English-style dates; Spanish month names that
// JS can't parse fall through to "" so the driver picks the date.
export function normDate(s: string): string {
  const d = (s || "").trim();
  if (!d) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
  // Append the current year first (deterministic across engines — a bare
  // `new Date("Jun 24")` parses to wildly wrong years in some runtimes), and
  // only if that already-has-a-year string fails, try the raw value.
  const yr = new Date().getFullYear();
  let dt = new Date(`${d} ${yr}`);
  if (isNaN(dt.getTime())) dt = new Date(d);
  if (isNaN(dt.getTime())) return "";
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
}

// Normalize a free-text/AI time to 24h HH:MM (what the picker/native input need).
export function normTime(s: string): string {
  const x = (s || "").trim().toLowerCase();
  if (!x) return "";
  let m = x.match(/^(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)$/);
  if (m) {
    let h = Number(m[1]) % 12;
    if (m[3].startsWith("p")) h += 12;
    return `${pad2(h)}:${m[2]}`;
  }
  m = x.match(/^(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)$/);
  if (m) {
    let h = Number(m[1]) % 12;
    if (m[2].startsWith("p")) h += 12;
    return `${pad2(h)}:00`;
  }
  m = x.match(/^(\d{1,2}):(\d{2})$/);
  if (m) return `${pad2(Number(m[1]))}:${m[2]}`;
  m = x.match(/^(\d{3,4})$/);
  if (m) {
    const v = m[1].padStart(4, "0");
    return `${v.slice(0, 2)}:${v.slice(2)}`;
  }
  return "";
}

// Combine the (already-normalized) date + time into an ISO timestamp. Parsed in
// the local timezone → so the calendar shows the right local pickup time.
// Returns null only when the date is missing/invalid — callers must treat null
// as "no scheduled time" and block, never silently save a timeless ride.
export function buildScheduledAt(date: string, time: string): string | null {
  const d = (date || "").trim();
  if (!d) return null;
  const t = (time || "").trim() || "00:00";
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d}T${t}` : `${d} ${new Date().getFullYear()} ${t}`;
  const parsed = new Date(iso);
  return isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

// Format a YYYY-MM-DD value for display in the user's locale (e.g. "Mon, Jun 24").
// Empty/invalid → "".
export function formatDateDisplay(date: string, locale: string): string {
  const d = (date || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return "";
  const [y, mo, da] = d.split("-").map(Number);
  const dt = new Date(y, mo - 1, da);
  if (isNaN(dt.getTime())) return "";
  return new Intl.DateTimeFormat(locale, { weekday: "short", month: "short", day: "numeric" }).format(dt);
}

// Format an HH:MM (24h) value for display as 12h with AM/PM (e.g. "6:30 AM").
// Empty/invalid → "".
export function formatTimeDisplay(time: string, locale: string): string {
  const t = (time || "").trim();
  const m = t.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return "";
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return "";
  const dt = new Date(2000, 0, 1, h, mi);
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(dt);
}
