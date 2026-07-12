/** Client API for the Volt Blog admin dashboard (owner only, cookie session). */
import { fmtApiDetail } from "@/lib/booking";

export interface BlogConfigT {
  voice: string | null;
  audience: string | null;
  key_themes: string[];
  avoid_topics: string[];
  image_style: string | null;
  cadence_per_week: number;
  autopublish: boolean;
  paused: boolean;
  languages: string[];
  embed_token: string;
  gsc_site_url: string | null;
  gsc_connected: boolean;
  gsc_connected_email: string | null;
}

export interface BlogKeywordT {
  id: number;
  keyword: string;
  lang: string;
  source: string;
  volume_est: number | null;
  difficulty_est: number | null;
  score: number | null;
  status: string;
  notes: string | null;
}

export interface BlogInternalLinkT {
  href: string;
  text: string;
}

export interface BlogFaqT {
  q: string;
  a: string;
}

export interface BlogPostT {
  id: number;
  slug: string;
  keyword_id: number | null;
  title_en: string;
  title_es: string | null;
  excerpt_en: string | null;
  excerpt_es: string | null;
  body_md_en: string | null;
  body_md_es: string | null;
  hero_url: string | null;
  hero_alt: string | null;
  status: string;
  publish_at: string | null;
  published_at: string | null;
  render_progress: number;
  render_stage: string | null;
  keyword: string | null;
  internal_links: BlogInternalLinkT[];
  faq: BlogFaqT[];
  created_at: string;
}

export interface BlogAnalyticsT {
  gsc: Array<Record<string, unknown>>;
  psi: Record<string, unknown> | null;
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

export const getBlogConfig = () => jget<BlogConfigT>("/v1/blog/admin/config");
export const putBlogConfig = (patch: Partial<BlogConfigT>) =>
  jsend<BlogConfigT>("/v1/blog/admin/config", "PUT", patch);

export const listBlogKeywords = (status?: string) =>
  jget<BlogKeywordT[]>(`/v1/blog/admin/keywords${status ? `?status=${status}` : ""}`);
export const addBlogKeyword = (keyword: string, lang: string) =>
  jsend<BlogKeywordT>("/v1/blog/admin/keywords", "POST", { keyword, lang });
export const setBlogKeywordStatus = (id: number, status: string) =>
  jsend<BlogKeywordT>(`/v1/blog/admin/keywords/${id}/status`, "POST", { status });
export const discoverBlogKeywords = () =>
  jsend<{ found?: number; promoted?: number; skipped?: string }>("/v1/blog/admin/discover", "POST");

export const listBlogPosts = () => jget<BlogPostT[]>("/v1/blog/admin/posts");
export const generateBlogPost = (opts: { keyword_id?: number; keyword?: string }) =>
  jsend<BlogPostT>("/v1/blog/admin/generate", "POST", opts);
export const patchBlogPost = (id: number, patch: Partial<BlogPostT>) =>
  jsend<BlogPostT>(`/v1/blog/admin/posts/${id}`, "PATCH", patch);
export const publishBlogPost = (id: number) =>
  jsend<BlogPostT>(`/v1/blog/admin/posts/${id}/publish`, "POST");
export const setBlogPostStatus = (id: number, status: string) =>
  jsend<BlogPostT>(`/v1/blog/admin/posts/${id}/status`, "POST", { status });

export const getBlogAnalytics = () => jget<BlogAnalyticsT>("/v1/blog/admin/analytics");
