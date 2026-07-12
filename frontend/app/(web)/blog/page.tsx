import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { fetchBlogList, heroFor } from "@/lib/blog";
import { SITE_ORIGIN } from "@/lib/seoRoutes";

export const dynamic = "force-dynamic";

type SearchParams = { [k: string]: string | string[] | undefined };

function langOf(sp: SearchParams): "en" | "es" {
  const v = Array.isArray(sp.lang) ? sp.lang[0] : sp.lang;
  return v === "es" ? "es" : "en";
}

const T = {
  en: {
    title: "Blog — Black Volt Mobility · Denver Luxury EV Transfers",
    heading: "The Black Volt Blog",
    sub: "Guides and tips for private luxury EV transfers across Denver, DEN airport, and the Colorado mountains.",
    read: "Read guide",
    empty: "New guides are on the way — check back soon.",
    other: "Leer en español",
  },
  es: {
    title: "Blog — Black Volt Mobility · Traslados EV de Lujo en Denver",
    heading: "El Blog de Black Volt",
    sub: "Guías y consejos para traslados privados en EV de lujo por Denver, el aeropuerto DEN y las montañas de Colorado.",
    read: "Leer guía",
    empty: "Pronto habrá nuevas guías — vuelve pronto.",
    other: "Read in English",
  },
};

export async function generateMetadata({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<Metadata> {
  const lang = langOf(searchParams);
  const t = T[lang];
  return {
    title: t.title,
    description: t.sub,
    alternates: {
      canonical: "/blog",
      languages: { en: "/blog", es: "/blog?lang=es" },
    },
    openGraph: { title: t.heading, description: t.sub, url: `${SITE_ORIGIN}/blog`, type: "website" },
  };
}

function fmtDate(iso: string | null, lang: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(lang === "es" ? "es-US" : "en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "America/Denver",
    });
  } catch {
    return "";
  }
}

export default async function BlogPage({ searchParams }: { searchParams: SearchParams }) {
  // Redirect shim: legacy Soro deep links (?post=slug / ?slug=slug) → canonical article URL.
  const legacy = searchParams.post ?? searchParams.slug;
  const legacySlug = Array.isArray(legacy) ? legacy[0] : legacy;
  if (legacySlug) redirect(`/blog/${encodeURIComponent(legacySlug)}`);

  const lang = langOf(searchParams);
  const t = T[lang];
  const suffix = lang === "es" ? "?lang=es" : "";
  const posts = await fetchBlogList(lang);

  return (
    <section style={{ maxWidth: 860, margin: "0 auto", padding: "20px 16px 64px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, color: "var(--arctic)", margin: 0 }}>
          {t.heading}
        </h1>
        <Link href={lang === "es" ? "/blog" : "/blog?lang=es"} style={{ fontSize: 13, color: "var(--volt)" }}>
          {t.other}
        </Link>
      </div>
      <p style={{ color: "var(--fg2)", fontSize: 15, lineHeight: 1.5, margin: "10px 0 26px" }}>
        {t.sub}
      </p>

      {posts.length === 0 ? (
        <p style={{ color: "var(--fg3)" }}>{t.empty}</p>
      ) : (
        <div style={{ display: "grid", gap: 18 }}>
          {posts.map((p) => (
            <Link
              key={p.slug}
              href={`/blog/${p.slug}${suffix}`}
              style={{
                display: "block",
                border: "1px solid var(--hairline, #23232b)",
                borderRadius: 14,
                overflow: "hidden",
                background: "var(--void)",
                textDecoration: "none",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={heroFor(p)}
                alt={p.hero_alt || p.title}
                loading="lazy"
                style={{ width: "100%", height: 180, objectFit: "cover", display: "block" }}
              />
              <div style={{ padding: "14px 16px 18px" }}>
                <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 6 }}>
                  {fmtDate(p.published_at, lang)}
                </div>
                <h2 style={{ fontSize: 19, fontWeight: 700, color: "var(--arctic)", margin: "0 0 8px" }}>
                  {p.title}
                </h2>
                {p.excerpt ? (
                  <p style={{ fontSize: 14, color: "var(--fg2)", lineHeight: 1.5, margin: "0 0 10px" }}>
                    {p.excerpt}
                  </p>
                ) : null}
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--volt)" }}>{t.read} →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
