/* Tenant brand/profile settings (dashboard) + public profile feed (/d/{slug}). */

import { fmtApiDetail } from "./booking";

// The single-tenant MVP's public profile slug — matches the seeded tenant
// (backend tenancy.DEFAULT_TENANT_SLUG = "ender-ocando"). The app's own nav/CTAs
// must point here; a wrong slug 404s the live profile lookup.
export const PUBLIC_PROFILE_SLUG = "ender-ocando";

export interface PaymentsStatus {
  connected: boolean;
  live: boolean;
  env: string;
}

export interface NotificationsStatus {
  available: boolean;
  sms: boolean;
  calls: boolean;
}

export interface TenantSettings {
  slug: string;
  name: string;
  tagline: string | null;
  bio: string | null;
  instagram: string | null;
  website: string | null;
  vehicle: string | null;
  city: string | null;
  phone: string | null;
  brand_color: string | null;
  rating: number | null;
  since_year: number | null;
  logo_url: string | null;
  photo_url: string | null;
  payments: PaymentsStatus;
  notifications: NotificationsStatus;
}

export interface PublicProfile {
  slug: string;
  name: string;
  tagline: string | null;
  bio: string | null;
  instagram: string | null;
  website: string | null;
  vehicle: string | null;
  city: string | null;
  brand_color: string | null;
  logo_url: string | null;
  photo_url: string | null;
  rating: number | null;
  rides_total: number;
  years_active: number | null;
  // Present only when the viewer is a registered/signed-in client (the backend
  // gates this — anonymous visitors never receive it).
  phone?: string | null;
}

export type TenantSettingsInput = {
  name?: string;
  tagline?: string | null;
  bio?: string | null;
  instagram?: string | null;
  website?: string | null;
  vehicle?: string | null;
  city?: string | null;
  phone?: string | null;
  brand_color?: string | null;
  rating?: number | null;
  since_year?: number | null;
};

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
  return r.json();
}

export async function getTenantSettings(): Promise<TenantSettings> {
  return jget<TenantSettings>("/v1/tenant/settings");
}

export async function updateTenantSettings(body: TenantSettingsInput): Promise<TenantSettings> {
  const r = await fetch("/api/v1/tenant/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `settings:${r.status}`));
  }
  return r.json();
}

export async function uploadTenantAsset(
  kind: "logo" | "photo",
  file: File,
): Promise<TenantSettings> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`/api/v1/tenant/${kind}`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `upload:${r.status}`));
  }
  return r.json();
}

// Canonical PUBLIC site origin (where customers book), derived from the current
// origin. The driver dashboard lives on the `app.` subdomain; customer-facing
// links (profile share, QR, "Book a ride") must point at the apex host so the
// booking funnel and per-driver pricing work — never the dashboard host. Strips a
// leading `app.` label and leaves localhost/apex untouched; `NEXT_PUBLIC_PUBLIC_ORIGIN`
// overrides when set. Host-agnostic so it also holds for the multi-tenant SaaS path.
export function publicSiteOrigin(): string {
  const override = process.env.NEXT_PUBLIC_PUBLIC_ORIGIN;
  if (override) return override.replace(/\/+$/, "");
  const origin =
    typeof window !== "undefined" ? window.location.origin : "https://blackvoltmobility.com";
  return origin.replace("://app.", "://");
}

// Canonical shareable URL for a driver's public profile (`/d/{slug}`), always on
// the public (apex) host so the shared link/QR never lands a customer on the
// dashboard subdomain.
export function publicProfileUrl(slug: string): string {
  return `${publicSiteOrigin()}/d/${encodeURIComponent(slug)}`;
}

// ── Social link normalization ────────────────────────────────────────────────
// Drivers paste anything into the Instagram field — a full share URL with a
// `?igsh=…` tracking param, an `@handle`, or a bare handle. Reduce all of them to
// the canonical handle so the link resolves (never `instagram.com/https://…`).
export function instagramHandle(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let s = raw.trim();
  if (!s) return null;
  const m = s.match(/instagram\.com\/([^/?#]+)/i);
  if (m) s = m[1];
  s = s
    .replace(/^@/, "")
    .replace(/[/?#].*$/, "")
    .trim();
  return s || null;
}

// Full Instagram profile URL for a normalized handle, or null when unusable.
export function instagramUrl(raw: string | null | undefined): string | null {
  const h = instagramHandle(raw);
  return h ? `https://instagram.com/${h}` : null;
}

// Browsable website URL — prepend https:// when the driver omits the scheme.
export function websiteUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = raw.trim();
  if (!s) return null;
  return /^https?:\/\//i.test(s) ? s : `https://${s}`;
}

// Clean website label for display: drop scheme, leading `www.`, and trailing slash.
export function websiteLabel(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = raw.trim();
  if (!s) return null;
  return s
    .replace(/^https?:\/\//i, "")
    .replace(/^www\./i, "")
    .replace(/\/+$/, "");
}

// Public — returns null on 404 (unknown slug). Sends the session cookie so a
// registered/signed-in viewer also receives the driver's direct phone (the
// backend gates that field; anonymous visitors never get it).
export async function getPublicProfile(slug: string): Promise<PublicProfile | null> {
  const r = await fetch(`/api/v1/tenants/${encodeURIComponent(slug)}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`profile:${r.status}`);
  return r.json();
}
