import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchBlogPost, type BlogPostDetail } from "@/lib/blog";
import { renderMarkdown } from "@/lib/markdown";
import { SITE_ORIGIN } from "@/lib/seoRoutes";

export const dynamic = "force-dynamic";

type SearchParams = { [k: string]: string | string[] | undefined };

function langOf(sp: SearchParams): "en" | "es" {
  const v = Array.isArray(sp.lang) ? sp.lang[0] : sp.lang;
  return v === "es" ? "es" : "en";
}

const T = {
  en: { book: "Book your ride", faq: "Frequently asked questions", related: "Keep reading", back: "← All guides", other: "Leer en español", updated: "Updated" },
  es: { book: "Reserva tu viaje", faq: "Preguntas frecuentes", related: "Sigue leyendo", back: "← Todas las guías", other: "Read in English", updated: "Actualizado" },
};

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: { slug: string };
  searchParams: SearchParams;
}): Promise<Metadata> {
  const lang = langOf(searchParams);
  const post = await fetchBlogPost(params.slug, lang);
  if (!post) return { title: "Not found" };
  const canonical = `/blog/${post.slug}`;
  return {
    title: `${post.title} | Black Volt Mobility`,
    description: post.excerpt || undefined,
    alternates: {
      canonical,
      languages: { en: canonical, es: `${canonical}?lang=es` },
    },
    openGraph: {
      title: post.title,
      description: post.excerpt || undefined,
      url: `${SITE_ORIGIN}${canonical}`,
      type: "article",
      images: post.hero_url ? [{ url: post.hero_url }] : undefined,
    },
  };
}

function fmtDate(iso: string | null, lang: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(lang === "es" ? "es-US" : "en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "America/Denver",
    });
  } catch {
    return "";
  }
}

/** JSON-LD with `<` escaped so a stray char can't break out of the script tag. */
function jsonLd(post: BlogPostDetail, lang: string): string {
  const url = `${SITE_ORIGIN}/blog/${post.slug}`;
  const graph: Record<string, unknown>[] = [
    {
      "@type": "BlogPosting",
      headline: post.title,
      description: post.excerpt || undefined,
      ...(post.hero_url ? { image: [post.hero_url] } : {}),
      datePublished: post.published_at || undefined,
      dateModified: post.updated_at || post.published_at || undefined,
      inLanguage: lang,
      author: { "@type": "Organization", name: "Black Volt Mobility" },
      publisher: { "@type": "Organization", name: "Black Volt Mobility" },
      mainEntityOfPage: url,
    },
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Home", item: SITE_ORIGIN },
        { "@type": "ListItem", position: 2, name: "Blog", item: `${SITE_ORIGIN}/blog` },
        { "@type": "ListItem", position: 3, name: post.title, item: url },
      ],
    },
  ];
  if (post.faq && post.faq.length) {
    graph.push({
      "@type": "FAQPage",
      mainEntity: post.faq.map((f) => ({
        "@type": "Question",
        name: f.q,
        acceptedAnswer: { "@type": "Answer", text: f.a },
      })),
    });
  }
  return JSON.stringify({ "@context": "https://schema.org", "@graph": graph }).replace(/</g, "\\u003c");
}

export default async function BlogArticle({
  params,
  searchParams,
}: {
  params: { slug: string };
  searchParams: SearchParams;
}) {
  const lang = langOf(searchParams);
  const suffix = lang === "es" ? "?lang=es" : "";
  const post = await fetchBlogPost(params.slug, lang);
  if (!post) notFound();
  const t = T[lang];
  const bodyHtml = renderMarkdown(post.body_md);

  return (
    <article style={{ maxWidth: 760, margin: "0 auto", padding: "16px 16px 72px" }}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(post, lang) }} />
      <style
        dangerouslySetInnerHTML={{
          __html:
            ".bv-article-body h2{font-size:22px;font-weight:700;color:var(--arctic);margin:28px 0 10px;line-height:1.3}" +
            ".bv-article-body h3{font-size:18px;font-weight:700;color:var(--arctic);margin:22px 0 8px}" +
            ".bv-article-body p{margin:0 0 15px}" +
            ".bv-article-body ul{margin:0 0 15px;padding-left:22px;list-style:disc}" +
            ".bv-article-body li{margin:0 0 7px}" +
            ".bv-article-body a{color:var(--volt);text-decoration:underline}" +
            ".bv-article-body strong{color:var(--arctic);font-weight:700}" +
            ".bv-article-body code{background:var(--obsidian);padding:1px 5px;border-radius:4px;font-size:.9em}",
        }}
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <Link href={`/blog${suffix}`} style={{ fontSize: 13, color: "var(--fg2)" }}>{t.back}</Link>
        {post.has_es ? (
          <Link href={`/blog/${post.slug}${lang === "es" ? "" : "?lang=es"}`} style={{ fontSize: 13, color: "var(--volt)" }}>
            {t.other}
          </Link>
        ) : null}
      </div>

      {post.hero_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={post.hero_url}
          alt={post.hero_alt || post.title}
          style={{ width: "100%", maxHeight: 380, objectFit: "cover", borderRadius: 14, display: "block", marginBottom: 18 }}
        />
      ) : null}

      <h1 style={{ fontSize: 32, fontWeight: 800, color: "var(--arctic)", lineHeight: 1.2, margin: "0 0 10px" }}>
        {post.title}
      </h1>
      {post.published_at ? (
        <div style={{ fontSize: 13, color: "var(--fg3)", marginBottom: 22 }}>{fmtDate(post.published_at, lang)}</div>
      ) : null}

      <div
        className="bv-article-body"
        style={{ color: "var(--arctic)", fontSize: 16, lineHeight: 1.7 }}
        dangerouslySetInnerHTML={{ __html: bodyHtml }}
      />

      {post.faq && post.faq.length ? (
        <section style={{ marginTop: 34 }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--arctic)", margin: "0 0 14px" }}>{t.faq}</h2>
          <div style={{ display: "grid", gap: 12 }}>
            {post.faq.map((f, i) => (
              <div key={i} style={{ border: "1px solid var(--hairline, #23232b)", borderRadius: 12, padding: "12px 14px" }}>
                <div style={{ fontWeight: 600, color: "var(--arctic)", marginBottom: 6 }}>{f.q}</div>
                <div style={{ color: "var(--fg2)", fontSize: 15, lineHeight: 1.6 }}>{f.a}</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div style={{ marginTop: 36, textAlign: "center" }}>
        <Link
          href="/book"
          style={{
            display: "inline-block",
            padding: "13px 26px",
            borderRadius: 10,
            background: "var(--volt)",
            color: "var(--void)",
            fontWeight: 700,
            textDecoration: "none",
          }}
        >
          ⚡ {t.book}
        </Link>
      </div>
    </article>
  );
}
