/* Customer reviews API: public submit/list + admin moderation + review-request invites. */

export interface PublicReview {
  author_name: string;
  rating: number;
  body: string;
  verified: boolean;
  owner_reply: string | null;
  created_at: string;
}

export interface AdminReview {
  id: number;
  tenant_id: number;
  ride_id: number | null;
  author_name: string;
  author_email: string | null;
  rating: number;
  body: string;
  status: "pending" | "approved" | "rejected";
  show_on_home: boolean;
  featured: boolean;
  verified: boolean;
  source: string;
  owner_reply: string | null;
  created_at: string;
  approved_at: string | null;
}

export interface ReviewCandidate {
  ride_id: number;
  client_id: number | null;
  name: string;
  email: string | null;
  phone: string | null;
  route: string;
  when: string | null;
}

export interface InviteResult {
  id: number;
  token: string;
  link: string;
  message: string;
  sms_href: string;
  email_status: string | null;
}

function detailOf(d: unknown, fallback: string): string {
  if (d && typeof d === "object" && "detail" in d) {
    const v = (d as { detail?: unknown }).detail;
    if (typeof v === "string") return v;
  }
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

async function unwrap<T>(r: Response, tag: string): Promise<T> {
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(detailOf(d, `${tag}:${r.status}`));
  }
  return r.json();
}

// ─── public ───────────────────────────────────────────────────────────────

export async function listPublicReviews(
  opts: { surface?: string; tenantId?: number; limit?: number } = {},
): Promise<PublicReview[]> {
  const p = new URLSearchParams({ surface: opts.surface ?? "home" });
  if (opts.tenantId) p.set("tenant_id", String(opts.tenantId));
  if (opts.limit) p.set("limit", String(opts.limit));
  const r = await fetch(`/api/v1/reviews/public?${p.toString()}`, { cache: "no-store" });
  if (!r.ok) return [];
  return r.json();
}

export interface SubmitReviewInput {
  rating: number;
  body: string;
  author_name: string;
  author_email?: string;
  token?: string;
  ride_id?: number;
}

export async function submitReview(
  input: SubmitReviewInput,
): Promise<{ ok: boolean; status: string; verified: boolean }> {
  return unwrap(await send("/v1/reviews", "POST", input), "review");
}

export async function getReviewInvite(
  token: string,
): Promise<{ author_name: string | null; used: boolean }> {
  const r = await fetch(`/api/v1/reviews/invite/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`invite:${r.status}`);
  return r.json();
}

// ─── admin ────────────────────────────────────────────────────────────────

export async function listAdminReviews(status?: string): Promise<AdminReview[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const r = await fetch(`/api/v1/reviews/admin${q}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`reviews:${r.status}`);
  return r.json();
}

export interface ReviewPatch {
  status?: "pending" | "approved" | "rejected";
  show_on_home?: boolean;
  featured?: boolean;
  owner_reply?: string;
}

export async function patchReview(id: number, patch: ReviewPatch): Promise<AdminReview> {
  return unwrap(await send(`/v1/reviews/admin/${id}`, "PATCH", patch), "reviews");
}

export async function deleteReview(id: number): Promise<void> {
  const r = await send(`/v1/reviews/admin/${id}`, "DELETE");
  if (!r.ok && r.status !== 404) throw new Error(`reviews:${r.status}`);
}

export async function listReviewCandidates(q?: string): Promise<ReviewCandidate[]> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  const r = await fetch(`/api/v1/reviews/admin/candidates${qs}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`candidates:${r.status}`);
  return r.json();
}

export interface CreateInviteInput {
  ride_id?: number;
  client_id?: number;
  to_email?: string;
  to_phone?: string;
  author_name?: string;
  channels?: string[];
  lang?: string;
}

export async function createReviewInvite(input: CreateInviteInput): Promise<InviteResult> {
  return unwrap(await send("/v1/reviews/admin/invites", "POST", input), "invite");
}
