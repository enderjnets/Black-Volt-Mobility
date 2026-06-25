/* Passenger self-service profile (same-origin /api → backend). */
import { fmtApiDetail } from "./booking";

export type ConversationPref = "chat" | "quiet" | "no_pref";
export type TemperaturePref = "cooler" | "warmer" | "no_pref";
export type MusicPref = "none" | "soft" | "driver_choice" | "no_pref";

/** Standing ride preferences. Mirrors the backend RidePreferences schema. */
export interface RidePreferences {
  conversation: ConversationPref;
  temperature: TemperaturePref;
  music: MusicPref;
  luggage_help: boolean;
  pet: boolean;
  notes: string;
}

/** Max length of the free-text note — kept in sync with the backend (RIDE_NOTES_MAX). */
export const RIDE_NOTES_MAX = 500;

export function defaultRidePreferences(): RidePreferences {
  return {
    conversation: "no_pref",
    temperature: "no_pref",
    music: "no_pref",
    luggage_help: false,
    pet: false,
    notes: "",
  };
}

/** Single-select dimensions: field, icon, label key, and options (value → i18n key). */
export const RIDE_PREF_CHOICES = [
  {
    field: "conversation",
    icon: "message-circle",
    label: "acct.ridePrefs.conversation",
    options: [
      { value: "chat", label: "acct.ridePrefs.conversation.chat" },
      { value: "quiet", label: "acct.ridePrefs.conversation.quiet" },
      { value: "no_pref", label: "acct.ridePrefs.noPref" },
    ],
  },
  {
    field: "temperature",
    icon: "thermometer",
    label: "acct.ridePrefs.temperature",
    options: [
      { value: "cooler", label: "acct.ridePrefs.temperature.cooler" },
      { value: "warmer", label: "acct.ridePrefs.temperature.warmer" },
      { value: "no_pref", label: "acct.ridePrefs.noPref" },
    ],
  },
  {
    field: "music",
    icon: "music",
    label: "acct.ridePrefs.music",
    options: [
      { value: "none", label: "acct.ridePrefs.music.none" },
      { value: "soft", label: "acct.ridePrefs.music.soft" },
      { value: "driver_choice", label: "acct.ridePrefs.music.driverChoice" },
      { value: "no_pref", label: "acct.ridePrefs.noPref" },
    ],
  },
] as const;

/** Boolean amenity toggles. */
export const RIDE_PREF_TOGGLES = [
  { field: "luggage_help", icon: "briefcase", label: "acct.ridePrefs.luggage" },
  { field: "pet", icon: "paw-print", label: "acct.ridePrefs.pet" },
] as const;

export interface Profile {
  first_name: string | null;
  last_name: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  home_address: string | null;
  sms_consent: boolean;
  email_consent: boolean;
  lang: string | null;
  ride_preferences: RidePreferences;
  profile_complete: boolean;
}

export type ProfilePatch = Partial<{
  first_name: string;
  last_name: string;
  phone: string;
  home_address: string;
  sms_consent: boolean;
  email_consent: boolean;
  lang: string;
  // Partial is allowed: the backend merges it onto the stored preferences.
  ride_preferences: Partial<RidePreferences>;
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
