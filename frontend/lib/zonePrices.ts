/* Live zone prices for server components (SEO pages, homepage).
 *
 * Teaser prices used to be hardcoded and drifted from the quote engine every time the
 * owner tuned the Rates dashboard (v0.66.2 and v0.66.3 were both manual re-sync
 * releases). Now the pages read the same effective map the quote engine uses —
 * GET /rate-config returns {**DEFAULT_ZONE_PRICES, **tenant override} — cached with a
 * short ISR window so a Rates edit reaches the public site within minutes, no deploy.
 * The hardcoded `priceFrom` in seoRoutes.ts remains only as a fallback when the
 * backend is unreachable at render time.
 */
import type { SeoRoute } from "./seoRoutes";

const API = process.env.INTERNAL_API_URL || "http://localhost:8012";

export async function getZonePrices(): Promise<Record<string, number> | null> {
  try {
    const res = await fetch(`${API}/api/v1/rate-config`, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    const data = await res.json();
    const zones = data?.zone_prices;
    return zones && typeof zones === "object" ? zones : null;
  } catch {
    return null;
  }
}

/** Effective "from $X" for a route: live zone price when available, else the fallback. */
export function routePrice(
  route: Pick<SeoRoute, "zoneKey" | "priceFrom">,
  zones: Record<string, number> | null,
): number | null {
  const live = route.zoneKey && zones ? zones[route.zoneKey] : undefined;
  if (typeof live === "number" && live > 0) return Math.round(live);
  return route.priceFrom;
}

/** Substitute the {{price}} token FAQ answers use for the current fare. */
export function fillPrice(text: string, price: number | null): string {
  return text.replace(/\{\{price\}\}/g, price != null ? `$${price}` : "an instant quote");
}
