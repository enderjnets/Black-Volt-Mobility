/* Platform stats (Uber/Lyft/Co-op screenshot import) API client. Staff-only. */

import { fmtApiDetail } from "./booking";
import { normalizeImage, SmartError } from "./smart";

export type Platform = "uber" | "lyft" | "coop" | "other";

export interface PlatformDraft {
  platform: Platform | null;
  period_label: string | null;
  period_start: string | null;
  period_end: string | null;
  trips: number | null;
  earnings: number | null;
  online_hours: number | null;
  currency: string | null;
}

export interface PlatformStat {
  id: number;
  platform: Platform;
  period_label: string | null;
  period_start: string | null;
  period_end: string | null;
  trips: number | null;
  earnings: number | null;
  online_hours: number | null;
  currency: string;
  created_at: string | null;
}

export interface PlatformSummary {
  days: number;
  totals: {
    earnings: number;
    trips: number;
    online_hours: number;
    per_trip: number | null;
    per_hour: number | null;
  };
  by_platform: { platform: Platform; earnings: number; trips: number; hours: number }[];
  private_revenue: number;
  comparison: { platform: number; private: number; private_share: number | null };
  imports: PlatformStat[];
}

export async function getPlatformSummary(days = 30): Promise<PlatformSummary> {
  const r = await fetch(`/api/v1/stats/platform?days=${days}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`platform:${r.status}`);
  return r.json();
}

// Upload screenshot(s) → AI-parsed draft (the driver reviews before saving).
export async function extractPlatform(
  files: File[],
): Promise<{ fields: PlatformDraft; simulated: boolean; image_count: number }> {
  const fd = new FormData();
  for (const f of files) {
    let out = f;
    try {
      out = await normalizeImage(f);
    } catch (e) {
      if (e instanceof SmartError) throw e;
    }
    fd.append("files", out);
  }
  const r = await fetch("/api/v1/stats/platform/extract", {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new SmartError(typeof d.detail === "string" ? d.detail : `http_${r.status}`);
  }
  return r.json();
}

export async function savePlatform(body: {
  platform: string;
  period_label?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  trips?: number | null;
  earnings?: number | null;
  online_hours?: number | null;
  currency?: string | null;
}): Promise<PlatformStat> {
  const r = await fetch("/api/v1/stats/platform", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `platform:${r.status}`));
  }
  return r.json();
}

export async function deletePlatform(id: number): Promise<void> {
  const r = await fetch(`/api/v1/stats/platform/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `platform:${r.status}`));
  }
}
