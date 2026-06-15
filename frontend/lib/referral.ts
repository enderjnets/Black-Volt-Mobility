/* Referral attribution (client side).
 *
 * When a visitor lands on a driver's public link (`/d/{slug}`) we remember that
 * slug so the next Google sign-in can be attributed to that driver. The backend
 * is the source of truth for the *permanent* designated driver (first-touch): we
 * only carry the "pending" referral hint of the most recent link they opened.
 */

const REF_KEY = "bv_ref";
const MAX_AGE_DAYS = 90;

function slugOk(slug: string | null | undefined): slug is string {
  return !!slug && /^[a-z0-9-]{1,80}$/.test(slug);
}

/** Remember the driver slug a visitor arrived through. No-op on the server. */
export function setRef(slug: string): void {
  if (typeof document === "undefined" || !slugOk(slug)) return;
  const maxAge = MAX_AGE_DAYS * 24 * 60 * 60;
  document.cookie = `${REF_KEY}=${encodeURIComponent(slug)}; path=/; max-age=${maxAge}; samesite=lax`;
}

/** The pending referral slug, or null. */
export function getRef(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${REF_KEY}=([^;]*)`));
  if (!m) return null;
  const slug = decodeURIComponent(m[1]);
  return slugOk(slug) ? slug : null;
}
