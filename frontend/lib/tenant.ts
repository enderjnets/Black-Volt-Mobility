/* Tenant brand/profile settings (dashboard) + public profile feed (/d/{slug}). */

import { fmtApiDetail } from "./booking";

// The single-tenant MVP's public profile slug — matches the seeded tenant
// (backend tenancy.DEFAULT_TENANT_SLUG = "black-volt"). The app's own nav/CTAs
// must point here; a wrong slug 404s the live profile lookup.
export const PUBLIC_PROFILE_SLUG = "black-volt";

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

// Canonical shareable URL for a driver's public profile (`/d/{slug}`). Uses the
// current origin in the browser (so it's correct per environment) and falls back
// to the production host during SSR.
export function publicProfileUrl(slug: string): string {
  const origin =
    typeof window !== "undefined" ? window.location.origin : "https://app.blackvoltmobility.com";
  return `${origin}/d/${encodeURIComponent(slug)}`;
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
