import { redirect } from "next/navigation";

import { Profile } from "@/components/bv/web/Profile";

// Deprecated profile slugs kept working after the brand→driver rename: redirect to
// the canonical URL so already-shared links and printed QR codes still resolve and
// the address bar shows the current slug. (The backend also aliases these for the
// profile fetch + referral attribution.)
const SLUG_ALIASES: Record<string, string> = { "black-volt": "ender-ocando" };

export default function Page({ params }: { params: { slug: string } }) {
  const canonical = SLUG_ALIASES[params.slug];
  if (canonical) redirect(`/d/${canonical}`);
  return <Profile slug={params.slug} />;
}
