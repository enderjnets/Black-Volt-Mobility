/* Client helpers for the Black Volt legal-agreement API (same-origin /api → backend).
   Mirrors lib/auth.ts: same base URL + credentials. */

export interface Agreement {
  doc_type: string;
  version: string;
  audience: string;
  lang: string;
  title: string;
  content_md: string;
}

export async function getAgreement(docType: string, lang: string): Promise<Agreement> {
  const r = await fetch(`/api/v1/agreements/${encodeURIComponent(docType)}?lang=${encodeURIComponent(lang)}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`agreement_fetch_failed:${r.status}`);
  return r.json();
}

export async function acceptAgreement(
  docType: string,
  args: { version: string; lang: string; signedName?: string },
): Promise<void> {
  const r = await fetch(`/api/v1/agreements/${encodeURIComponent(docType)}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      version: args.version,
      lang: args.lang,
      signed_name: args.signedName,
    }),
  });
  // Throw on non-OK so the caller can detect 409 (stale version) / 422 (missing name).
  if (!r.ok) throw new Error(`agreement_accept_failed:${r.status}`);
}
