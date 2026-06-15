"use client";

import { useEffect, useState } from "react";

import { Profile } from "@/components/bv/web/Profile";
import { fetchMe } from "@/lib/auth";
import { getRef } from "@/lib/referral";
import { PUBLIC_PROFILE_SLUG } from "@/lib/tenant";

/* "Your Driver" tab. Resolves whose profile to show:
 *   1. signed-in passenger  → their designated driver (session tenant slug)
 *   2. anonymous w/ referral → the driver whose link they arrived through
 *   3. otherwise             → the default Black Volt profile
 */
export default function Page() {
  const [slug, setSlug] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchMe()
      .then((me) => {
        if (!alive) return;
        setSlug((me.authenticated && me.tenant_slug) || getRef() || PUBLIC_PROFILE_SLUG);
      })
      .catch(() => {
        if (alive) setSlug(getRef() || PUBLIC_PROFILE_SLUG);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!slug) return null;
  return <Profile slug={slug} />;
}
