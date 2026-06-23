/* Passenger self-service profile (same-origin /api → backend). */
import { fmtApiDetail } from "./booking";

export interface Profile {
  first_name: string | null;
  last_name: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  home_address: string | null;
  sms_consent: boolean;
  profile_complete: boolean;
}

export type ProfilePatch = Partial<{
  first_name: string;
  last_name: string;
  phone: string;
  home_address: string;
  sms_consent: boolean;
}>;

export async function getProfile(): Promise<Profile> {
  const r = await fetch("/api/v1/me/profile", { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`profile:${r.status}`);
  return r.json();
}

export async function updateProfile(changes: ProfilePatch): Promise<Profile> {
  const r = await fetch("/api/v1/me/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(changes),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `profile:${r.status}`));
  }
  return r.json();
}

/** Light client-side phone check for UX only — the backend is authoritative.
 *  Accepts a 10-digit US number (with formatting) or a +E.164 international one. */
export function looksLikePhone(raw: string): boolean {
  const t = raw.trim();
  if (!t) return false;
  if (t.startsWith("+")) return /^\+[1-9]\d{7,14}$/.test(t.replace(/[^\d+]/g, ""));
  const digits = t.replace(/\D/g, "");
  return digits.length === 10 || (digits.length === 11 && digits.startsWith("1"));
}
