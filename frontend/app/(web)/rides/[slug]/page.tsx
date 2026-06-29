import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import RouteTrust from "@/components/bv/web/RouteTrust";
import {
  SEO_ROUTES,
  SITE_ORIGIN,
  bookHref,
  getRoute,
  getRouteLabel,
  routeHero,
  routeMap,
} from "@/lib/seoRoutes";

export function generateStaticParams() {
  return SEO_ROUTES.map((r) => ({ slug: r.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const route = getRoute(params.slug);
  if (!route) return {};
  const path = `/rides/${route.slug}`;
  const hero = routeHero(route);
  return {
    title: route.metaTitle,
    description: route.metaDescription,
    alternates: { canonical: path },
    openGraph: {
      title: route.metaTitle,
      description: route.metaDescription,
      url: `${SITE_ORIGIN}${path}`,
      type: "website",
      images: [{ url: hero.src, alt: hero.alt }],
    },
  };
}

const fmtPrice = (n: number) => `$${n.toLocaleString("en-US")}`;

export default function RidePage({ params }: { params: { slug: string } }) {
  const route = getRoute(params.slug);
  if (!route) notFound();

  const path = `/rides/${route.slug}`;
  const priceLabel = route.priceFrom != null ? `from ${fmtPrice(route.priceFrom)}` : "Instant quote";
  const hero = routeHero(route);

  // Structured data: Service + FAQPage + BreadcrumbList. Helps local SEO and can earn
  // rich results (FAQ accordions, breadcrumbs) in Google.
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Service",
        name: route.metaTitle,
        serviceType: "Luxury electric chauffeur transfer",
        provider: {
          "@type": "LocalBusiness",
          name: "Black Volt Mobility",
          url: SITE_ORIGIN,
          areaServed: "Denver metropolitan area, Colorado",
        },
        areaServed: { "@type": "City", name: "Denver" },
        description: route.metaDescription,
        url: `${SITE_ORIGIN}${path}`,
        ...(route.priceFrom != null && {
          offers: {
            "@type": "Offer",
            price: route.priceFrom,
            priceCurrency: "USD",
            description: `Private luxury EV transfer ${priceLabel}`,
          },
        }),
      },
      {
        "@type": "FAQPage",
        mainEntity: route.faq.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: SITE_ORIGIN },
          { "@type": "ListItem", position: 2, name: "Rides", item: `${SITE_ORIGIN}/rides` },
          { "@type": "ListItem", position: 3, name: route.shortLabel, item: `${SITE_ORIGIN}${path}` },
        ],
      },
    ],
  };

  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "20px 16px 64px" }}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <nav style={{ fontSize: 13, color: "var(--fg3)", marginBottom: 14 }}>
        <Link href="/rides" style={{ color: "var(--fg3)", textDecoration: "none" }}>
          ← All routes
        </Link>
      </nav>

      {/* Hero */}
      <header
        style={{
          position: "relative",
          aspectRatio: "16 / 10",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          border: "1px solid var(--line)",
          marginBottom: 20,
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={hero.src}
          alt={hero.alt}
          width={1200}
          height={750}
          loading="eager"
          decoding="async"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(180deg, rgba(10,10,15,0.25) 0%, rgba(10,10,15,0.55) 55%, rgba(10,10,15,0.92) 100%)",
          }}
        />
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: "18px 18px 16px" }}>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 28,
              lineHeight: 1.15,
              fontWeight: 700,
              margin: "0 0 10px",
              color: "var(--arctic)",
              textShadow: "0 2px 14px rgba(0,0,0,0.6)",
            }}
          >
            {route.h1}
          </h1>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {[`${priceLabel}`, `~${route.distanceMi} mi`, `~${route.durationMin} min`, "Luxury electric SUV"].map(
              (chip) => (
                <span
                  key={chip}
                  style={{
                    fontSize: 12.5,
                    fontWeight: 600,
                    color: "var(--volt)",
                    background: "rgba(10,10,15,0.62)",
                    border: "1px solid var(--volt-border)",
                    borderRadius: "var(--radius-full)",
                    padding: "5px 12px",
                    backdropFilter: "blur(4px)",
                  }}
                >
                  {chip}
                </span>
              ),
            )}
          </div>
        </div>
      </header>

      <p style={{ fontSize: 16, lineHeight: 1.65, color: "var(--fg2)", margin: "0 0 20px" }}>
        {route.lede}
      </p>

      <a
        href={bookHref(route)}
        style={{
          display: "inline-block",
          background: "var(--volt)",
          color: "#0A0A0F",
          fontWeight: 700,
          fontSize: 15,
          textDecoration: "none",
          padding: "13px 26px",
          borderRadius: "var(--radius-md)",
          boxShadow: "var(--shadow-volt)",
        }}
      >
        Get your instant price →
      </a>

      {/* Route map */}
      <figure style={{ margin: "26px 0 0" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={routeMap(route)}
          alt={`Map of the ${route.shortLabel} route driven by Black Volt Mobility`}
          width={1200}
          height={675}
          loading="lazy"
          decoding="async"
          style={{
            width: "100%",
            height: "auto",
            display: "block",
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--line)",
          }}
        />
        <figcaption style={{ marginTop: 8, fontSize: 12.5, color: "var(--fg3)", textAlign: "center" }}>
          {route.shortLabel} · ~{route.distanceMi} mi · ~{route.durationMin} min door-to-door
        </figcaption>
      </figure>

      {/* Trust signals */}
      <RouteTrust />

      {/* Why this ride */}
      <section style={{ marginTop: 34 }}>
        <h2 style={{ fontSize: 19, fontWeight: 700, margin: "0 0 12px", color: "var(--arctic)" }}>
          Why ride with Black Volt
        </h2>
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 10 }}>
          {route.highlights.map((h) => (
            <li
              key={h}
              style={{ display: "flex", gap: 10, fontSize: 15, lineHeight: 1.5, color: "var(--fg2)" }}
            >
              <span style={{ color: "var(--volt)", fontWeight: 700 }}>✓</span>
              <span>{h}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Testimonials — only when real ones exist (never placeholders) */}
      {route.testimonials && route.testimonials.length > 0 && (
        <section style={{ marginTop: 34 }}>
          <h2 style={{ fontSize: 19, fontWeight: 700, margin: "0 0 14px", color: "var(--arctic)" }}>
            What riders say
          </h2>
          <div style={{ display: "grid", gap: 12 }}>
            {route.testimonials.map((t) => (
              <blockquote
                key={t.author}
                style={{
                  margin: 0,
                  padding: 16,
                  background: "var(--obsidian-2)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-lg)",
                }}
              >
                <p style={{ margin: "0 0 8px", fontSize: 15, lineHeight: 1.55, color: "var(--fg1)" }}>
                  “{t.quote}”
                </p>
                <cite style={{ fontSize: 13, color: "var(--fg3)", fontStyle: "normal" }}>— {t.author}</cite>
              </blockquote>
            ))}
          </div>
        </section>
      )}

      {/* FAQ */}
      <section style={{ marginTop: 34 }}>
        <h2 style={{ fontSize: 19, fontWeight: 700, margin: "0 0 14px", color: "var(--arctic)" }}>
          Frequently asked questions
        </h2>
        <div style={{ display: "grid", gap: 16 }}>
          {route.faq.map((f) => (
            <div key={f.q}>
              <h3 style={{ fontSize: 15.5, fontWeight: 600, margin: "0 0 5px", color: "var(--fg1)" }}>
                {f.q}
              </h3>
              <p style={{ fontSize: 14.5, lineHeight: 1.6, margin: 0, color: "var(--fg2)" }}>{f.a}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA repeat */}
      <section
        style={{
          marginTop: 36,
          padding: 22,
          background: "var(--obsidian-2)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius-lg)",
          textAlign: "center",
        }}
      >
        <p style={{ fontSize: 16, fontWeight: 600, margin: "0 0 14px", color: "var(--arctic)" }}>
          Ready to ride {route.shortLabel}?
        </p>
        <a
          href={bookHref(route)}
          style={{
            display: "inline-block",
            background: "var(--volt)",
            color: "#0A0A0F",
            fontWeight: 700,
            fontSize: 15,
            textDecoration: "none",
            padding: "13px 26px",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--shadow-volt)",
          }}
        >
          See your price &amp; book →
        </a>
      </section>

      {/* Related */}
      {route.related.length > 0 && (
        <section style={{ marginTop: 36 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 12px", color: "var(--arctic)" }}>
            Other popular routes
          </h2>
          <div style={{ display: "grid", gap: 8 }}>
            {route.related.map((slug) => (
              <Link
                key={slug}
                href={`/rides/${slug}`}
                style={{
                  fontSize: 14.5,
                  color: "var(--volt)",
                  textDecoration: "none",
                  padding: "10px 14px",
                  background: "var(--obsidian-3)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-md)",
                }}
              >
                {getRouteLabel(slug)} →
              </Link>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
