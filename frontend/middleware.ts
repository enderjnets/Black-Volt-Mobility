import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Send `www.` to the bare domain, permanently.
 *
 * Both hostnames answered 200 with identical content and nothing said which was the real
 * one, so Google filed the homepage as "Duplicate without user-selected canonical" and
 * declined to index it — the most important page on the site. Canonical tags now declare
 * the apex; this makes the duplicate stop existing at all, which is the half a crawler
 * never has to interpret.
 *
 * Only `www.` hosts are touched: the dashboard lives on `app.` and must not be redirected.
 */
export function middleware(req: NextRequest) {
  const host = req.headers.get("host") || "";
  if (!host.toLowerCase().startsWith("www.")) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.host = host.slice(4);
  url.port = "";
  url.protocol = "https:";
  return NextResponse.redirect(url, 308); // permanent, and preserves the request method
}

export const config = {
  // Skip Next's own assets and the API proxy: a redirect there would cost a round trip on
  // every request for no SEO benefit.
  matcher: ["/((?!_next/|api/|favicon.ico).*)"],
};
