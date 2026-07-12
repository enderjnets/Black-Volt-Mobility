/**
 * Server-side data helpers for the public Volt Blog (SSR). Fetches the FastAPI backend
 * directly via INTERNAL_API_URL, per request (pages are force-dynamic), mirroring the
 * events landing pattern.
 */

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://localhost:8012";

export interface BlogInternalLink {
  href: string;
  text: string;
}

export interface BlogFaq {
  q: string;
  a: string;
}

export interface BlogListItem {
  slug: string;
  lang: string;
  title: string;
  excerpt: string | null;
  hero_url: string | null;
  hero_alt: string | null;
  published_at: string | null;
  has_es: boolean;
}

export interface BlogPostDetail extends BlogListItem {
  body_md: string | null;
  updated_at: string | null;
  faq: BlogFaq[];
  internal_links: BlogInternalLink[];
  keyword: string | null;
}

// Curated brand heroes used when a post has no generated hero image (deterministic per
// slug so a given article always shows the same one). Zero external dependency.
const DEFAULT_HEROES = ["/assets/ev9-coors-field.webp", "/assets/ev9-charging.webp"];

export function heroFor(item: { slug: string; hero_url: string | null }): string {
  if (item.hero_url) return item.hero_url;
  let h = 0;
  for (const c of item.slug) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return DEFAULT_HEROES[h % DEFAULT_HEROES.length];
}

export async function fetchBlogList(lang: string): Promise<BlogListItem[]> {
  try {
    const res = await fetch(
      `${INTERNAL_API_URL}/api/v1/blog/public?lang=${encodeURIComponent(lang)}`,
      { cache: "no-store" },
    );
    if (!res.ok) return [];
    return (await res.json()) as BlogListItem[];
  } catch {
    return [];
  }
}

export async function fetchBlogPost(
  slug: string,
  lang: string,
): Promise<BlogPostDetail | null> {
  try {
    const res = await fetch(
      `${INTERNAL_API_URL}/api/v1/blog/public/${encodeURIComponent(slug)}?lang=${encodeURIComponent(lang)}`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    return (await res.json()) as BlogPostDetail;
  } catch {
    return null;
  }
}
