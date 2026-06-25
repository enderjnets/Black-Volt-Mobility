/* Passenger saved-address book (same-origin /api → backend).
   Scoped server-side to the signed-in passenger; the client only ever sees
   its own addresses. */
import { fmtApiDetail } from "./booking";

export interface SavedAddress {
  id: number;
  label: string | null;
  address: string;
  is_default: boolean;
  created_at: string | null;
}

export type AddressInput = { label?: string | null; address: string; is_default?: boolean };
export type AddressPatch = Partial<{ label: string | null; address: string; is_default: boolean }>;

async function jbody(method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function fail(r: Response, d: unknown): never {
  throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `addr:${r.status}`));
}

export async function getAddresses(): Promise<SavedAddress[]> {
  const r = await fetch("/api/v1/me/addresses", { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`addr:${r.status}`);
  const d = await r.json();
  return (d.addresses ?? []) as SavedAddress[];
}

export async function createAddress(body: AddressInput): Promise<SavedAddress> {
  const r = await jbody("POST", "/api/v1/me/addresses", body);
  if (!r.ok) fail(r, await r.json().catch(() => ({})));
  return r.json();
}

export async function updateAddress(id: number, body: AddressPatch): Promise<SavedAddress> {
  const r = await jbody("PATCH", `/api/v1/me/addresses/${id}`, body);
  if (!r.ok) fail(r, await r.json().catch(() => ({})));
  return r.json();
}

export async function setDefaultAddress(id: number): Promise<SavedAddress> {
  const r = await jbody("POST", `/api/v1/me/addresses/${id}/default`);
  if (!r.ok) fail(r, await r.json().catch(() => ({})));
  return r.json();
}

export async function deleteAddress(id: number): Promise<void> {
  const r = await jbody("DELETE", `/api/v1/me/addresses/${id}`);
  if (!r.ok && r.status !== 204) fail(r, await r.json().catch(() => ({})));
}
