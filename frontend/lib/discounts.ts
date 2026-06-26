/* Driver discount-codes API. Backs the Discounts dashboard panel. */

export interface DiscountCode {
  id: number;
  code: string;
  discount_pct: number;
  max_uses: number | null;
  uses: number;
  expires_at: string | null;
  active: boolean;
  created_at: string;
}

function detailOf(d: unknown, fallback: string): string {
  if (typeof d === "string") return d;
  return fallback;
}

async function send(path: string, method: string, body?: unknown): Promise<Response> {
  return fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function listDiscounts(): Promise<DiscountCode[]> {
  const r = await fetch("/api/v1/discounts", { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`discounts:${r.status}`);
  return r.json();
}

export interface CreateDiscountInput {
  code: string;
  discount_pct: number;
  max_uses?: number | null;
  expires_at?: string | null;
}

export async function createDiscount(input: CreateDiscountInput): Promise<DiscountCode> {
  const r = await send("/v1/discounts", "POST", input);
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `discounts:${r.status}`));
  }
  return r.json();
}

export async function patchDiscount(id: number, active: boolean): Promise<DiscountCode> {
  const r = await send(`/v1/discounts/${id}`, "PATCH", { active });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `discounts:${r.status}`));
  }
  return r.json();
}

export async function deleteDiscount(id: number): Promise<void> {
  const r = await send(`/v1/discounts/${id}`, "DELETE");
  if (!r.ok && r.status !== 204) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `discounts:${r.status}`));
  }
}

// ── Admin-only helpers ────────────────────────────────────────────────────────

export interface DriverOption {
  tenant_id: number;
  email: string;
}

export async function listDrivers(): Promise<DriverOption[]> {
  const r = await fetch("/api/v1/discounts/drivers", { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`drivers:${r.status}`);
  return r.json();
}

export interface CreateCampaignInput {
  name: string;
  discount_pct: number;
  max_uses?: number | null;
  expires_at?: string | null;
  driver_tenant_ids: number[];
}

export interface CampaignCode {
  code: string;
  discount_pct: number;
  tenant_id?: number;
}

export interface CampaignResult {
  campaign: Record<string, unknown>;
  codes: CampaignCode[];
}

export async function createCampaign(input: CreateCampaignInput): Promise<CampaignResult> {
  const r = await send("/v1/discounts/campaigns", "POST", input);
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf((d as { detail?: unknown }).detail, `campaigns:${r.status}`));
  }
  return r.json();
}
