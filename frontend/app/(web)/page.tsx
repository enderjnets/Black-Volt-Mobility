import { getZonePrices } from "@/lib/zonePrices";
import { Landing } from "@/components/bv/web/Landing";
import { SITE_ORIGIN } from "@/lib/seoRoutes";

// LocalBusiness structured data for local SEO. Service-area business (no public
// street address). Phone is published only when set via env (never hardcoded).
const localBusinessLd = {
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "@id": `${SITE_ORIGIN}/#business`,
  name: "Black Volt Mobility",
  description:
    "Luxury electric chauffeur service in Denver: door-to-door rides across the metro, DEN airport transfers both ways, and mountain transfers to Vail, Breckenridge & Aspen.",
  url: SITE_ORIGIN,
  slogan: "Silent Power. Premium Arrival.",
  ...(process.env.NEXT_PUBLIC_BUSINESS_PHONE && {
    telephone: process.env.NEXT_PUBLIC_BUSINESS_PHONE,
  }),
  areaServed: [
    { "@type": "City", name: "Denver" },
    { "@type": "City", name: "Aurora" },
    { "@type": "City", name: "Boulder" },
    { "@type": "City", name: "Vail" },
    { "@type": "City", name: "Breckenridge" },
    { "@type": "City", name: "Aspen" },
  ],
  address: { "@type": "PostalAddress", addressRegion: "CO", addressCountry: "US" },
  priceRange: "$$$",
};

export const revalidate = 300; // live zone prices for Popular routes

export default async function Page() {
  const zonePrices = await getZonePrices();
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(localBusinessLd) }}
      />
      {/* Preload the LCP hero so it starts downloading before the JS/fonts, not after.
          React hoists this <link> into <head>; matches the <img> in Landing. */}
      <link
        rel="preload"
        as="image"
        type="image/avif"
        href="/assets/ev9-coors-field.avif"
        imageSrcSet="/assets/ev9-coors-field-800w.avif 800w, /assets/ev9-coors-field.avif 1600w"
        imageSizes="(max-width: 800px) 100vw, 1040px"
        fetchPriority="high"
      />
      <Landing zonePrices={zonePrices} />
    </>
  );
}
