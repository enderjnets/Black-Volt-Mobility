import type { MetadataRoute } from "next";

import { SEO_ROUTES, SITE_ORIGIN } from "@/lib/seoRoutes";

const API = process.env.INTERNAL_API_URL || "http://localhost:8012";

// Static, public, indexable pages. The dashboard (app. host) and authenticated
// passenger pages are intentionally excluded.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPages = [
    { path: "/", priority: 1.0, changeFrequency: "weekly" as const },
    { path: "/book", priority: 0.9, changeFrequency: "monthly" as const },
    { path: "/rides", priority: 0.8, changeFrequency: "weekly" as const },
    { path: "/blog", priority: 0.7, changeFrequency: "weekly" as const },
    { path: "/terms", priority: 0.2, changeFrequency: "yearly" as const },
    { path: "/privacy", priority: 0.2, changeFrequency: "yearly" as const },
  ];
  const routePages = SEO_ROUTES.map((r) => ({
    path: `/rides/${r.slug}`,
    priority: 0.7,
    changeFrequency: "monthly" as const,
  }));

  // Published upcoming events (best-effort — a fetch failure keeps the static map).
  let eventPages: { path: string; priority: 0.6; changeFrequency: "daily" }[] = [];
  try {
    // Timeout so /sitemap.xml never blocks on backend health (it was a static asset).
    const r = await fetch(`${API}/api/v1/events/public`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (r.ok) {
      const events = (await r.json()) as { slug: string }[];
      eventPages = events.map((e) => ({
        path: `/events/${e.slug}`,
        priority: 0.6 as const,
        changeFrequency: "daily" as const,
      }));
    }
  } catch {
    eventPages = [];
  }

  // Published blog posts (best-effort — same timeout guard as events).
  let blogPages: { path: string; priority: 0.6; changeFrequency: "weekly" }[] = [];
  try {
    const r = await fetch(`${API}/api/v1/blog/public`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (r.ok) {
      const posts = (await r.json()) as { slug: string }[];
      blogPages = posts.map((p) => ({
        path: `/blog/${p.slug}`,
        priority: 0.6 as const,
        changeFrequency: "weekly" as const,
      }));
    }
  } catch {
    blogPages = [];
  }

  return [...staticPages, ...routePages, ...eventPages, ...blogPages].map((p) => ({
    url: `${SITE_ORIGIN}${p.path}`,
    changeFrequency: p.changeFrequency,
    priority: p.priority,
  }));
}
