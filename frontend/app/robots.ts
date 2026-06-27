import type { MetadataRoute } from "next";

import { SITE_ORIGIN } from "@/lib/seoRoutes";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Authenticated/transactional areas add no SEO value and shouldn't be crawled.
      disallow: ["/trips", "/api/"],
    },
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
    host: SITE_ORIGIN,
  };
}
