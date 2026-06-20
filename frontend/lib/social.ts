/* Social-media module API client. Staff-only, tenant-scoped. */

import { fmtApiDetail } from "./booking";

export type SocialPlatform = "instagram" | "facebook" | "tiktok";
export type PostStatus =
  | "draft"
  | "render_requested"
  | "rendered"
  | "approved"
  | "scheduled"
  | "published"
  | "failed";

export interface SocialPost {
  id: number;
  topic: string | null;
  script: string | null;
  caption: string | null;
  hashtags: string | null;
  media_path: string | null;
  cover_path: string | null;
  simulated_render: boolean;
  targets: SocialPlatform[];
  status: PostStatus;
  scheduled_at: string | null;
  published_at: string | null;
  external_ids: Record<string, string>;
  views: number;
  likes: number;
  comments: number;
  lang: string;
  created_at: string | null;
  source?: "ai" | "template";
}

export type ReplyStatus = "pending" | "drafted" | "approved" | "sent" | "dismissed";

export interface SocialInteraction {
  id: number;
  post_id: number | null;
  platform: SocialPlatform;
  author_handle: string | null;
  text: string | null;
  lang: string;
  ai_draft: string | null;
  reply_status: ReplyStatus;
  replied_at: string | null;
  created_at: string | null;
  source?: "ai" | "template";
}

export interface SocialAccount {
  id: number | null;
  platform: SocialPlatform;
  display_name: string | null;
  status: string;
  connected: boolean;
  token_expires_at: string | null;
}

export interface SocialAnalytics {
  posts_total: number;
  posts_published: number;
  by_status: Record<string, number>;
  views: number;
  likes: number;
  comments: number;
  pending_replies: number;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
  return r.json();
}

async function jsend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`));
  }
  return r.json();
}

// ── posts ──────────────────────────────────────────────────────────────────
export async function listPosts(status?: string): Promise<SocialPost[]> {
  return jget<SocialPost[]>(`/v1/social/posts${status ? `?status=${encodeURIComponent(status)}` : ""}`);
}

export async function generatePost(body: {
  topic?: string;
  angle?: string;
  lang: string;
  targets?: SocialPlatform[];
}): Promise<SocialPost> {
  return jsend<SocialPost>("/v1/social/posts/generate", "POST", body);
}

export async function updatePost(
  id: number,
  body: Partial<{ script: string; caption: string; hashtags: string; targets: SocialPlatform[]; scheduled_at: string | null }>,
): Promise<SocialPost> {
  return jsend<SocialPost>(`/v1/social/posts/${id}`, "PATCH", body);
}

export async function deletePost(id: number): Promise<void> {
  const r = await fetch(`/api/v1/social/posts/${id}`, { method: "DELETE", credentials: "include" });
  if (!r.ok && r.status !== 204) throw new Error(`delete:${r.status}`);
}

export async function renderPost(id: number): Promise<SocialPost> {
  return jsend<SocialPost>(`/v1/social/posts/${id}/render`, "POST");
}

export async function approvePost(id: number, scheduledAt?: string | null): Promise<SocialPost> {
  return jsend<SocialPost>(`/v1/social/posts/${id}/approve`, "POST", { scheduled_at: scheduledAt ?? null });
}

export async function rejectPost(id: number): Promise<SocialPost> {
  return jsend<SocialPost>(`/v1/social/posts/${id}/reject`, "POST");
}

export async function publishPost(id: number): Promise<SocialPost> {
  return jsend<SocialPost>(`/v1/social/posts/${id}/publish`, "POST");
}

// ── inbox ──────────────────────────────────────────────────────────────────
export async function listInbox(status?: string): Promise<SocialInteraction[]> {
  return jget<SocialInteraction[]>(`/v1/social/inbox${status ? `?status=${encodeURIComponent(status)}` : ""}`);
}

export async function draftReply(id: number): Promise<SocialInteraction> {
  return jsend<SocialInteraction>(`/v1/social/inbox/${id}/draft`, "POST");
}

export async function sendReply(id: number, text?: string): Promise<SocialInteraction> {
  return jsend<SocialInteraction>(`/v1/social/inbox/${id}/reply`, "POST", { text: text ?? null });
}

export async function dismissInteraction(id: number): Promise<SocialInteraction> {
  return jsend<SocialInteraction>(`/v1/social/inbox/${id}/dismiss`, "POST");
}

// ── accounts + analytics ─────────────────────────────────────────────────────
export async function listAccounts(): Promise<SocialAccount[]> {
  return jget<SocialAccount[]>("/v1/social/accounts");
}

export async function syncBufferChannels(): Promise<SocialAccount[]> {
  return jsend<SocialAccount[]>("/v1/social/accounts/sync", "POST");
}

export async function getAnalytics(): Promise<SocialAnalytics> {
  return jget<SocialAnalytics>("/v1/social/analytics");
}
