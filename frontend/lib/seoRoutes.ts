/* Curated SEO landing pages for high-intent local searches (route & use-case).
 *
 * IMPORTANT — these are hand-written, NOT auto-generated from a list. Each page has
 * genuinely unique copy, a real example fare (anchored to the live pricing engine), and
 * a route-specific FAQ. This is deliberate: Google demotes "doorway pages" (batches of
 * near-identical pages that only swap a place name). Quality over quantity — add a new
 * route here only when you can write real, distinct content for it.
 *
 * Example fares were taken from the live /quote engine (real Google Maps distances,
 * 2026-06-27). They're shown as "from $X" and every CTA links to a live instant quote.
 */
import { PUBLIC_PROFILE_SLUG } from "./tenant";

export const SITE_ORIGIN = "https://blackvoltmobility.com";

export interface FaqItem {
  q: string;
  a: string;
}

export interface SeoRoute {
  slug: string;
  /** <title> (≤60 chars ideal) */
  metaTitle: string;
  /** meta description (≤155 chars ideal) */
  metaDescription: string;
  /** on-page H1 */
  h1: string;
  /** short label used in lists/breadcrumbs */
  shortLabel: string;
  /** prefill for the booking form deep-link */
  prefillFrom: string;
  prefillTo: string;
  /** example fare in USD, shown as "from $X" (null → show "Instant quote") */
  priceFrom: number | null;
  distanceMi: number;
  durationMin: number;
  /** unique intro paragraph */
  lede: string;
  /** unique selling bullets for this route */
  highlights: string[];
  /** route-specific FAQ (also emitted as FAQPage JSON-LD) */
  faq: FaqItem[];
  /** related slugs for internal linking */
  related: string[];
  /** hero photo override (defaults by route category in routeHero) */
  heroImage?: string;
  heroAlt?: string;
  /** real customer testimonials — only rendered when present (never placeholders) */
  testimonials?: { quote: string; author: string }[];
}

export const SEO_ROUTES: SeoRoute[] = [
  {
    slug: "aurora-to-den-airport",
    metaTitle: "Aurora to DEN Airport — Luxury EV Car Service",
    metaDescription:
      "Private electric chauffeur from Aurora, CO to Denver International Airport (DEN). Flat, upfront fare, on-time pickups, luxury SUV. Book in seconds.",
    h1: "Aurora → Denver Airport (DEN) — Private EV Transfer",
    shortLabel: "Aurora → DEN",
    prefillFrom: "Aurora, CO",
    prefillTo: "Denver International Airport (DEN)",
    priceFrom: 110,
    distanceMi: 12,
    durationMin: 20,
    lede:
      "Skip the surge pricing and the mystery cars. Black Volt Mobility runs private, door-to-door airport transfers from anywhere in Aurora to Denver International (DEN) in a silent, spacious luxury electric SUV — driven by the owner, not a rotating gig driver.",
    highlights: [
      "Flat, upfront fare — quoted before you book, no surge",
      "Door-to-door from any Aurora neighborhood (Southlands, Saddle Rock, Tower, Heather Gardens)",
      "Flight-aware timing so you arrive with margin, never a rush",
      "Meet-and-greet on the return: we track your flight and adjust for delays",
      "Quiet, roomy Kia EV9 — luggage, car seats, and a calm ride",
    ],
    faq: [
      {
        q: "How far is Aurora from Denver International Airport?",
        a: "Most of Aurora is 12–20 miles from DEN, roughly a 20–30 minute drive depending on your neighborhood and traffic on E-470 or Peña Blvd. You'll see the exact distance and time on your quote.",
      },
      {
        q: "How much does an Aurora to DEN ride cost?",
        a: "Fares start around $110 for a private luxury SUV with a flat airport rate — the price is quoted upfront before you book, with no surge pricing.",
      },
      {
        q: "How early should I book my airport pickup?",
        a: "We recommend booking the night before for early-morning flights. We time the pickup to your flight so you arrive with comfortable margin, not a scramble.",
      },
      {
        q: "Do you track flights for airport pickups?",
        a: "Yes. For arrivals at DEN we monitor your flight and adjust the pickup time automatically if it's early or delayed, so your driver is there when you land.",
      },
    ],
    related: ["cherry-creek-to-den-airport", "dtc-corporate-airport-transfer", "boulder-to-den-airport"],
  },
  {
    slug: "cherry-creek-to-den-airport",
    metaTitle: "Cherry Creek to DEN Airport — Luxury Car Service",
    metaDescription:
      "Premium electric chauffeur from Cherry Creek to Denver International Airport (DEN). Upfront fare, on-time, luxury SUV. Book your private transfer.",
    h1: "Cherry Creek → Denver Airport (DEN) — Luxury EV Transfer",
    shortLabel: "Cherry Creek → DEN",
    prefillFrom: "Cherry Creek, Denver, CO",
    prefillTo: "Denver International Airport (DEN)",
    priceFrom: 110,
    distanceMi: 20,
    durationMin: 31,
    lede:
      "For Cherry Creek residents and guests at the Halcyon or Clayton, Black Volt Mobility is the polished way to DEN: a private luxury electric SUV, a professional owner-driver, and a fare you see before you confirm — no app roulette outside the boutiques.",
    highlights: [
      "Curbside pickup from Cherry Creek North, the Shops, and nearby hotels",
      "Upfront flat airport fare — confirmed before you ride",
      "Spotless luxury EV with room for luggage and shopping",
      "Discreet, professional, punctual — ideal for clients and guests",
      "Return meet-and-greet with live flight tracking",
    ],
    faq: [
      {
        q: "How long is the drive from Cherry Creek to DEN?",
        a: "About 20 miles and 30–40 minutes via I-25 and Peña Blvd, depending on time of day. Your exact route time appears on the quote.",
      },
      {
        q: "What does a Cherry Creek to airport ride cost?",
        a: "From about $110 for a private luxury SUV at a flat airport rate, quoted upfront with no surge.",
      },
      {
        q: "Can you pick up from a Cherry Creek hotel or store?",
        a: "Yes — we do curbside pickup from any Cherry Creek address, hotel, or storefront. Just enter the pickup spot when you book.",
      },
    ],
    related: ["aurora-to-den-airport", "dtc-corporate-airport-transfer", "denver-to-vail-private-transfer"],
  },
  {
    slug: "dtc-corporate-airport-transfer",
    metaTitle: "DTC Corporate Airport Transfer to DEN — Black Volt",
    metaDescription:
      "Corporate airport car service from the Denver Tech Center (DTC) to DEN. Reliable, professional, luxury EV. Upfront billing-friendly fares.",
    h1: "Denver Tech Center (DTC) → DEN — Corporate Airport Transfer",
    shortLabel: "DTC → DEN",
    prefillFrom: "Denver Tech Center, Greenwood Village, CO",
    prefillTo: "Denver International Airport (DEN)",
    priceFrom: 110,
    distanceMi: 22,
    durationMin: 25,
    lede:
      "When a client or executive flies in or out, the ride should reflect the company. Black Volt Mobility provides dependable corporate airport transfers between the Denver Tech Center and DEN in a quiet luxury electric SUV — punctual, professional, with a clean upfront fare that's easy to expense.",
    highlights: [
      "Reliable pickups from DTC offices, Greenwood Village, and Inverness",
      "Upfront, itemized fare — simple to expense or bill back",
      "Professional owner-driver, dressed for client-facing travel",
      "Quiet cabin for calls and email on the way to the airport",
      "Book for yourself, a visiting client, or a team member",
    ],
    faq: [
      {
        q: "Do you handle corporate or client airport pickups?",
        a: "Yes. You can book a ride for yourself, a visiting client, or a colleague — enter their pickup details and we'll handle the rest, including a return meet-and-greet with flight tracking.",
      },
      {
        q: "How much is a DTC to DEN corporate transfer?",
        a: "From about $110 for a private luxury SUV, quoted upfront so it's easy to approve and expense — no surge surprises.",
      },
      {
        q: "How long does the DTC to airport drive take?",
        a: "Roughly 22 miles and 25–35 minutes via I-25 and E-470/Peña Blvd, depending on traffic. The live quote shows your exact time.",
      },
    ],
    related: ["cherry-creek-to-den-airport", "aurora-to-den-airport", "boulder-to-den-airport"],
  },
  {
    slug: "boulder-to-den-airport",
    metaTitle: "Boulder to DEN Airport — Private Luxury EV Service",
    metaDescription:
      "Private electric chauffeur from Boulder, CO to Denver International Airport (DEN). Upfront fare, on-time, comfortable luxury SUV. Book now.",
    h1: "Boulder → Denver Airport (DEN) — Private EV Transfer",
    shortLabel: "Boulder → DEN",
    prefillFrom: "Boulder, CO",
    prefillTo: "Denver International Airport (DEN)",
    priceFrom: 165,
    distanceMi: 39,
    durationMin: 45,
    lede:
      "The Boulder-to-DEN run is long enough that the car matters. Black Volt Mobility makes it effortless: a private luxury electric SUV, a calm and quiet ride down the Northwest Parkway, and a fare you lock in before you go — no shared shuttles, no stops, no surge.",
    highlights: [
      "Direct, private ride from Boulder, Gunbarrel, or Niwot — no shuttle stops",
      "Comfortable for the 40-mile run: quiet cabin, room to relax",
      "Upfront fare confirmed before pickup",
      "Flight-aware timing for the longer drive",
      "Return meet-and-greet at DEN with live flight tracking",
    ],
    faq: [
      {
        q: "How far is Boulder from Denver Airport?",
        a: "About 39 miles and a 45–55 minute drive via the Northwest Parkway and E-470, traffic depending. Your quote shows the exact distance and time.",
      },
      {
        q: "How much is a Boulder to DEN ride?",
        a: "From about $165 for a private luxury SUV — quoted upfront, no surge, and far more comfortable than a shared shuttle.",
      },
      {
        q: "Is this better than an airport shuttle from Boulder?",
        a: "It's a private, direct ride — no other passengers, no stops, and a luxury EV instead of a van. You leave on your schedule and arrive faster and calmer.",
      },
    ],
    related: ["aurora-to-den-airport", "denver-to-vail-private-transfer", "dtc-corporate-airport-transfer"],
  },
  {
    slug: "red-rocks-concert-transportation",
    metaTitle: "Red Rocks Concert Transportation — Luxury EV Rides",
    metaDescription:
      "Private round-trip rides to Red Rocks Amphitheatre concerts in a luxury electric SUV. Skip parking & traffic. Upfront fare, door-to-door. Book now.",
    h1: "Red Rocks Concert Transportation — Private Round-Trip Rides",
    shortLabel: "Red Rocks concert rides",
    prefillFrom: "Downtown Denver, CO",
    prefillTo: "Red Rocks Amphitheatre, Morrison, CO",
    priceFrom: 140,
    distanceMi: 15,
    durationMin: 25,
    lede:
      "Red Rocks is unforgettable — the parking and the post-show traffic jam are not. Black Volt Mobility drops you right at the gate and picks you up after the encore in a luxury electric SUV, so you can actually enjoy the night without driving the canyon or hunting for a spot.",
    highlights: [
      "Door-to-gate drop-off — skip the lots and the uphill walk",
      "Guaranteed pickup after the show, no surge-priced scramble",
      "Designated driver for the whole group — enjoy the night safely",
      "Comfortable luxury EV for up to your party size",
      "Pickup from anywhere in the Denver metro",
    ],
    faq: [
      {
        q: "How does a round trip to Red Rocks work?",
        a: "We drop you at the entrance before the show and pick you up at a set spot after it ends — no parking, no canyon traffic, and a guaranteed ride home. Tell us your pickup address and show time when you book.",
      },
      {
        q: "How much does a Red Rocks ride cost?",
        a: "One-way fares start around $140 from central Denver in a private luxury SUV; round trips are quoted upfront based on your pickup point and wait time.",
      },
      {
        q: "Can you take a group to a concert?",
        a: "Yes — the luxury SUV seats your party comfortably, and one booking covers the whole group with a designated driver for the night.",
      },
    ],
    related: ["denver-to-vail-private-transfer", "aurora-to-den-airport", "cherry-creek-to-den-airport"],
  },
  {
    slug: "denver-to-vail-private-transfer",
    metaTitle: "Denver to Vail Private Car Transfer — Luxury EV",
    metaDescription:
      "Private luxury EV transfer from Denver & DEN airport to Vail. Door-to-door, upfront fare, ski-ready comfort. Book your mountain transfer.",
    h1: "Denver → Vail — Private Luxury Mountain Transfer",
    shortLabel: "Denver → Vail",
    prefillFrom: "Denver, CO",
    prefillTo: "Vail, CO",
    priceFrom: 349,
    distanceMi: 97,
    durationMin: 105,
    lede:
      "Trade the shared mountain shuttle for your own luxury EV. Black Volt Mobility drives you door-to-door from Denver or DEN airport straight to your Vail lodging — no extra stops, no waiting on other passengers, and a quiet, panoramic ride up I-70 with room for skis and luggage.",
    highlights: [
      "Direct private ride from Denver or DEN to any Vail address — no shuttle stops",
      "Room for ski/snowboard gear and full luggage",
      "Upfront flat-distance fare, locked in before you go",
      "Relax for the 2-hour I-70 drive in a quiet luxury cabin",
      "Round-trip and resort pickups available",
    ],
    faq: [
      {
        q: "How long is the drive from Denver to Vail?",
        a: "About 97 miles and roughly 1 hour 45 minutes up I-70 in good conditions; winter weather can add time. We plan the timing around your check-in or flight.",
      },
      {
        q: "How much is a private transfer from Denver to Vail?",
        a: "From about $349 for a private luxury SUV door-to-door — quoted upfront, with no per-seat shuttle pricing or surprises.",
      },
      {
        q: "Can you pick us up at DEN airport for a Vail transfer?",
        a: "Yes. We meet you at Denver International and drive straight to Vail, with space for everyone's luggage and ski gear. Enter DEN as your pickup when you book.",
      },
      {
        q: "Do you carry skis and snowboards?",
        a: "Yes — the luxury SUV has room for skis, boards, boot bags, and luggage for your group.",
      },
    ],
    related: ["denver-to-breckenridge-private-transfer", "denver-to-aspen-private-transfer", "boulder-to-den-airport"],
  },
  {
    slug: "denver-to-breckenridge-private-transfer",
    metaTitle: "Denver to Breckenridge Private Transfer — Luxury EV",
    metaDescription:
      "Private luxury EV transfer from Denver & DEN to Breckenridge. Door-to-door, ski-ready, upfront fare. Book your mountain ride.",
    h1: "Denver → Breckenridge — Private Luxury Mountain Transfer",
    shortLabel: "Denver → Breckenridge",
    prefillFrom: "Denver, CO",
    prefillTo: "Breckenridge, CO",
    priceFrom: 299,
    distanceMi: 81,
    durationMin: 95,
    lede:
      "Get to Breck on your own schedule. Black Volt Mobility runs private door-to-door transfers from Denver or DEN airport to Breckenridge in a luxury electric SUV — a calm, direct ride over the divide with space for skis, boards, and bags, and a fare you lock in before departure.",
    highlights: [
      "Private, direct ride to any Breckenridge condo or hotel",
      "Ski and snowboard gear welcome",
      "Upfront fare — no shared-van per-seat pricing",
      "Quiet, comfortable cabin for the climb over Eisenhower Tunnel",
      "DEN airport pickups and round trips available",
    ],
    faq: [
      {
        q: "How long does Denver to Breckenridge take?",
        a: "About 81 miles and roughly 1 hour 35 minutes via I-70 and Highway 9, weather permitting. Winter conditions over the pass can add time, which we plan for.",
      },
      {
        q: "What does a Denver to Breckenridge transfer cost?",
        a: "From about $299 for a private luxury SUV door-to-door, quoted upfront — no per-person shuttle fares.",
      },
      {
        q: "Can you pick us up from DEN for Breckenridge?",
        a: "Yes — we meet you at Denver International and drive directly to Breckenridge with room for all your gear. Set DEN as your pickup point when booking.",
      },
    ],
    related: ["denver-to-vail-private-transfer", "denver-to-aspen-private-transfer", "aurora-to-den-airport"],
  },
  {
    slug: "denver-to-aspen-private-transfer",
    metaTitle: "Denver to Aspen Private Car Transfer — Luxury EV",
    metaDescription:
      "Private luxury EV transfer from Denver & DEN airport to Aspen. Door-to-door comfort for the long mountain drive. Upfront fare. Book now.",
    h1: "Denver → Aspen — Private Luxury Mountain Transfer",
    shortLabel: "Denver → Aspen",
    prefillFrom: "Denver, CO",
    prefillTo: "Aspen, CO",
    priceFrom: 790,
    distanceMi: 159,
    durationMin: 205,
    lede:
      "Aspen is a long, beautiful drive — do it in comfort. Black Volt Mobility offers private door-to-door transfers from Denver or DEN airport to Aspen in a luxury electric SUV, a serene alternative to a connecting flight or a shared van, with one upfront fare for your whole party.",
    highlights: [
      "Private door-to-door ride to any Aspen or Snowmass address",
      "Comfortable for the scenic 3-hour-plus drive — stretch out and relax",
      "One upfront fare for the group, not per seat",
      "Plenty of room for luggage, skis, and gear",
      "A calm alternative to a connecting flight into ASE",
    ],
    faq: [
      {
        q: "How long is the drive from Denver to Aspen?",
        a: "About 159 miles and roughly 3 to 3.5 hours via I-70 and Highway 82 over Independence Pass season permitting (or via Glenwood in winter). We plan timing around your schedule.",
      },
      {
        q: "How much is a private car from Denver to Aspen?",
        a: "From about $790 for a private luxury SUV door-to-door for your whole party — quoted upfront, no per-person pricing.",
      },
      {
        q: "Is a private transfer better than flying to Aspen?",
        a: "For many travelers, yes — no connection, no baggage limits, no weather cancellations into ASE, and a door-to-door ride in a quiet luxury cabin on your own schedule.",
      },
    ],
    related: ["denver-to-vail-private-transfer", "denver-to-breckenridge-private-transfer", "cherry-creek-to-den-airport"],
  },
];

export function getRoute(slug: string): SeoRoute | undefined {
  return SEO_ROUTES.find((r) => r.slug === slug);
}

/** Human label for a slug (for internal links); falls back to the slug. */
export function getRouteLabel(slug: string): string {
  return getRoute(slug)?.shortLabel ?? slug;
}

/** Deep-link to the booking page with the trip prefilled + campaign attribution. */
export function bookHref(route: SeoRoute): string {
  const p = new URLSearchParams({
    from: route.prefillFrom,
    to: route.prefillTo,
    ref: PUBLIC_PROFILE_SLUG,
    utm_source: "site",
    utm_medium: "seo",
    utm_campaign: route.slug,
  });
  return `/book?${p.toString()}`;
}

/** Hero photo for a route — explicit override, else a sensible default by category. */
export function routeHero(route: SeoRoute): { src: string; alt: string } {
  if (route.heroImage) return { src: route.heroImage, alt: route.heroAlt ?? route.h1 };
  const outdoors = /vail|breckenridge|aspen|red-rocks/.test(route.slug);
  const src = outdoors ? "/assets/ev9-coors-field.jpg" : "/assets/ev9-charging.jpg";
  const alt =
    route.heroAlt ?? `Black Volt Mobility luxury electric SUV — ${route.shortLabel}`;
  return { src, alt };
}

/** Committed static route map (real OpenStreetMap basemap, brand-dark, with the route line). */
export function routeMap(route: SeoRoute): string {
  return `/assets/maps/${route.slug}.webp`;
}
