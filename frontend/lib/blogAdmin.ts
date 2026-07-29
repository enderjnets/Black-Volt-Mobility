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
  /** Why a `draft` was held back, keyed by language. Empty when the article passed. */
  quality_issues: Record<string, string[]>;
  created_at: string;
}

export interface BlogGscDayT {
  date: string;
  clicks?: number;
  impressions?: number;
  ctr?: number;
  top_queries?: Array<{
    query: string; clicks: number; impressions: number; ctr: number; position: number;
  }>;
}

/** One page of a self-measured speed audit. `verdict` marks each metric ok | warn. */
export interface BlogSpeedPageT {
  url: string;
  path: string;
  status: number | null;
  ttfb_ms?: number;
  total_ms?: number;
  html_kb?: number;
  compressed?: boolean;
  http_version?: string;
  blocking_scripts?: number;
  blocking_styles?: number;
  images_kb?: number;
  images_found?: number;
  images_counted?: number;
  error?: string;
  verdict: Record<string, "ok" | "warn">;
}

export interface BlogAnalyticsT {
  gsc: BlogGscDayT[];
  gsc_totals: { days: number; clicks: number; impressions: number; ctr: number };
  /** Our own measurement, not Lighthouse — `method` says so. Null until the first run. */
  speed: {
    method: string;
    measured_at: string;
    pages: BlogSpeedPageT[];
    summary: { pages: number; warnings: number; slowest_ttfb_ms: number };
  } | null;
  indexing: {
    checked: number;
    indexed: number;
    urls: Array<{ url: string; verdict?: string; coverage?: string; last_crawl?: string; error?: string }>;
  } | null;
  /** What the engine itself has produced — true today, unlike Search Console. */
  engine: {
    posts: Record<string, number>;
    last_published: string | null;
    keywords: Record<string, number>;
    keyword_sources: Record<string, number>;
    next_keyword: string | null;
  };
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
  jsend<{ status: string }>("/v1/blog/admin/generate", "POST", opts);

/** Write an article and wait for it to land.
 *
 * A bilingual article is two long model calls, which outlasts the 100s ceiling every proxy
 * in front of this app enforces — so the POST only starts the job and we watch the post
 * list for the new row. `onWait` is called every few seconds so the UI can show progress
 * instead of a frozen spinner.
 */
export async function generateBlogPostAndWait(
  opts: { keyword_id?: number; keyword?: string },
  onWait?: (elapsedSeconds: number) => void,
): Promise<BlogPostT[]> {
  const before = new Set((await listBlogPosts()).map((p) => p.id));
  await generateBlogPost(opts);
  const stepMs = 4000;
  const steps = 75; // ~5 minutes, well past the slowest observed generation
  for (let i = 1; i <= steps; i++) {
    await new Promise((r) => setTimeout(r, stepMs));
    onWait?.(Math.round((i * stepMs) / 1000));
    const posts = await listBlogPosts();
    if (posts.some((p) => !before.has(p.id))) return posts;
  }
  // The job may still finish; we simply stopped watching.
  throw new Error("blog.err.slow");
}
export const patchBlogPost = (id: number, patch: Partial<BlogPostT>) =>
  jsend<BlogPostT>(`/v1/blog/admin/posts/${id}`, "PATCH", patch);
export const publishBlogPost = (id: number) =>
  jsend<BlogPostT>(`/v1/blog/admin/posts/${id}/publish`, "POST");
export const setBlogPostStatus = (id: number, status: string) =>
  jsend<BlogPostT>(`/v1/blog/admin/posts/${id}/status`, "POST", { status });

export const getBlogAnalytics = () => jget<BlogAnalyticsT>("/v1/blog/admin/analytics");
export const autofillBlogConfig = () =>
  jsend<BlogConfigT>("/v1/blog/admin/config/autofill", "POST");
export const runBlogSpeed = () =>
  jsend<{ ok?: boolean; pages?: number; warnings?: number }>("/v1/blog/admin/speed/run", "POST");
export interface BlogSitemapT {
  expected?: string;
  /** Whether the saved Google permission allows submitting. `null` = Google did not say,
   *  so the action stays available rather than being hidden on a guess. */
  can_submit?: boolean | null;
  sitemaps?: Array<{
    path: string;
    last_submitted: string | null;
    /** Null means Google has never fetched it — the reason nothing is indexed. */
    last_downloaded: string | null;
    pending: boolean;
    warnings: number;
    errors: number;
  }>;
  /** `needs_reauth` = the stored Google token predates our write scope. */
  skipped?: string;
}

export const getBlogSitemap = () => jget<BlogSitemapT>("/v1/blog/admin/sitemap");
export const submitBlogSitemap = () =>
  jsend<{ ok?: boolean; path?: string; skipped?: string }>("/v1/blog/admin/sitemap/submit", "POST");

export const gscAuthorizeUrl = (siteUrl: string) =>
  jget<{ url: string }>(`/v1/blog/admin/gsc/authorize?site_url=${encodeURIComponent(siteUrl)}`);
