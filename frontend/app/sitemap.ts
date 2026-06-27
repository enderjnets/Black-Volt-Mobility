import type { MetadataRoute } from "next";

import { SEO_ROUTES, SITE_ORIGIN } from "@/lib/seoRoutes";

// Static, public, indexable pages. The dashboard (app. host) and authenticated
// passenger pages are intentionally excluded.
export default function sitemap(): MetadataRoute.Sitemap {
  const staticPages = [
    { path: "/", priority: 1.0, changeFrequency: "weekly" as const },
    { path: "/book", priority: 0.9, changeFrequency: "monthly" as const },
    { path: "/rides", priority: 0.8, changeFrequency: "weekly" as const },
    { path: "/terms", priority: 0.2, changeFrequency: "yearly" as const },
    { path: "/privacy", priority: 0.2, changeFrequency: "yearly" as const },
  ];
  const routePages = SEO_ROUTES.map((r) => ({
    path: `/rides/${r.slug}`,
    priority: 0.7,
    changeFrequency: "monthly" as const,
  }));
  return [...staticPages, ...routePages].map((p) => ({
    url: `${SITE_ORIGIN}${p.path}`,
    changeFrequency: p.changeFrequency,
    priority: p.priority,
  }));
}
