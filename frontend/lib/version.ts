export interface VersionEntry {
  version: string;
  date: string;
  title: string;
  changes: string[];
}

export const CURRENT_VERSION = "0.83.0";

export const CHANGELOG: VersionEntry[] = [
  {
    version: "0.83.0",
    date: "2026-07-20",
    title: "Sign in and get ride alerts in the Android app",
    changes: [
      "In the Black Volt Android app you can now sign in with your Google account using the phone's native account picker — one tap, no typing.",
      "Once you're signed in, the app registers for push notifications, so ride updates and driver messages reach you even when the app is closed.",
    ],
  },
  {
    version: "0.82.0",
    date: "2026-07-17",
    title: "Message your driver right from the trip",
    changes: [
      "Riders and their driver can now chat about a specific ride, inside the app — no more texting a phone number. On your trip, tap \"Message\" to open the conversation; the driver sees it on the ride and can reply.",
      "You get a push notification when the other person messages, and unread messages show a badge on the trip. Chat opens when the ride is booked and stays open until shortly after it's completed.",
    ],
  },
  {
    version: "0.81.1",
    date: "2026-07-17",
    title: "Fix: goal projection no longer errors before your first close",
    changes: [
      "Setting a client or revenue goal and viewing the projection used to fail if you'd logged activity but hadn't closed anyone yet. The \"how many conversations a day\" estimate now shows a sensible capped number instead of erroring.",
    ],
  },
  {
    version: "0.81.0",
    date: "2026-07-15",
    title: "Record customer tips on a ride",
    changes: [
      "You can now log a tip a customer leaves at the end of a ride. Open the ride, and under the payment method there's a new \"Add tip\" — pick how it was paid (it defaults to the ride's payment method, but you can change it — e.g. a cash tip on a card ride) and tap $5 / $10 / $20 or type a custom amount.",
      "Tips count toward your earnings: the day's revenue, weekly totals, per-client spend and My Stats now include them. Your average fare stays fare-only so pricing isn't skewed.",
      "The tip shows on the ride card as \"+$X\" under the fare, and you can edit or remove it anytime.",
    ],
  },
  {
    version: "0.80.2",
    date: "2026-07-12",
    title: "Public blog: Soro articles are back (coexisting with our engine)",
    changes: [
      "The public blog was showing our new engine only — which is still empty while we finish it — so the articles Soro publishes had disappeared. Soro is now back on the blog and keeps auto-publishing as before; our own posts will appear above Soro's as we publish them.",
    ],
  },
  {
    version: "0.80.1",
    date: "2026-07-12",
    title: "Blog Autopilot now writes full articles again (bilingual)",
    changes: [
      "Fixed the article writer dropping every post to a short template: the AI's formatted response wasn't being read correctly, so real 900-word guides never made it through. Now full English and Spanish articles generate reliably.",
    ],
  },
  {
    version: "0.80.0",
    date: "2026-07-12",
    title: "New: the Black Volt Blog — AI-written travel & ride guides",
    changes: [
      "Launched a blog of SEO guides for Denver airport transfers, Red Rocks concert rides, and mountain trips — written and kept fresh automatically, in English and Spanish.",
      "Each guide is a fast, native page (great for Google) with a hero image, FAQ, and a one-tap link to book.",
      "New owner control room: content calendar, keyword research, Brand DNA, Search Console analytics, and site-speed — all in the dashboard.",
    ],
  },
  {
    version: "0.79.0",
    date: "2026-07-11",
    title: "The \"Install app\" button now works on Safari (iPhone, iPad & Mac)",
    changes: [
      "Tapping \"Install app\" in Safari used to do nothing (Safari can't show Chrome's install pop-up). Now it opens a clear step-by-step card showing how to add Black Volt to your device.",
      "iPhone/iPad get the Add-to-Home-Screen steps via the Share button; Mac Safari gets the correct Add-to-Dock steps — no more misleading \"open the ⋮ menu\" hint that Safari doesn't have.",
      "The install banner now also appears for Mac Safari users, and its button opens the same instructions.",
    ],
  },
  {
    version: "0.78.0",
    date: "2026-07-10",
    title: "One page per show for multi-night events + a cleaner events dashboard",
    changes: [
      "Shows with more than one date (like a two-night Red Rocks run) now live on a single page with a date picker, instead of a separate page per night. Pick a date and the price, deposit, and booking update to that night — each date keeps its own fare.",
      "Old links to a specific night still work: they redirect to the unified page with that night already selected, so existing ads keep sending people to the right place.",
      "The events dashboard now separates active from archived events with a filter (Active / Archived / All), and groups a show's dates into one card — so past events stop cluttering the ones you're promoting.",
    ],
  },
  {
    version: "0.77.0",
    date: "2026-07-09",
    title: "Event prices now match the real fare to the venue",
    changes: [
      "Event pages now show the true round-trip price for the venue's area instead of a lower city-center estimate — so the price you see up front matches what you're quoted at checkout (e.g. Red Rocks now shows the correct fare for the foothills, not the inner-Denver rate).",
    ],
  },
  {
    version: "0.76.0",
    date: "2026-07-09",
    title: "Event booking is now measured end to end",
    changes: [
      "Booking a ride to an event now records the same steps we already track for regular rides — from viewing the event, to starting a booking, to paying — so we can see where people drop off and which events convert.",
      "This also lets our ad campaigns for specific events optimize toward real bookings instead of just clicks.",
    ],
  },
  {
    version: "0.75.0",
    date: "2026-07-09",
    title: "Event pages lead with the deposit + sticky mobile CTA",
    changes: [
      "Event pages now lead with the small reservation deposit (a third of the round trip) instead of the full price up front — e.g. \"Reserve for $138 today\" — with the full round-trip total shown right below as a breakdown, so the first number you see is the small one.",
      "On phones a Reserve button now stays pinned to the bottom of the screen while you read the event, so you can book without scrolling back up.",
      "The new event copy is fully bilingual (English and Spanish).",
    ],
  },
  {
    version: "0.74.0",
    date: "2026-07-08",
    title: "Joules knows what's on + faster hero",
    changes: [
      "Ask Joules \"what concerts or events are coming up?\" and it now answers with the real published events, their date and venue, the round-trip price (with the driver waiting) and the deposit — plus a link to book. It also knows the event/deposit policy, our service area and rider reviews.",
      "Joules is now hardened against prompt-injection: it politely refuses attempts to make it reveal its instructions or share confidential info (discount codes, other riders' details, internal pricing), and never leaks its own setup.",
      "Faster home page: the hero image now ships in AVIF (smaller, sharper) and the social-share images were slimmed down.",
    ],
  },
  {
    version: "0.73.0",
    date: "2026-07-07",
    title: "Sign in from your phone + a livelier Joules",
    changes: [
      "You can now sign in or create your account right from the phone app: a person icon in the top bar opens Google sign-in (it was only reachable on desktop or by starting a booking before).",
      "Joules, the chat assistant, now says hi: a few seconds after the page loads it gives its button a gentle nudge and floats a short question (\"Need a fare quote?\") so you know it's there — it settles down as soon as you open or dismiss it, and respects reduced-motion settings.",
    ],
  },
  {
    version: "0.72.1",
    date: "2026-07-06",
    title: "Fix: make the app installable",
    changes: [
      "Fixed why the \"Install app\" option wasn't showing on Android/Chrome: the app now registers its service worker on every visit (not only after enabling notifications) and meets Chrome's installability rules.",
      "Added a clear \"Install app\" button in the footer (and in the driver's Settings) that triggers the install prompt, with Add-to-Home-Screen instructions on iPhone.",
    ],
  },
  {
    version: "0.71.0",
    date: "2026-07-06",
    title: "Install the app + push notifications",
    changes: [
      "Black Volt is now installable to your phone's home screen — add it from your browser for a full-screen, app-like experience (both the rider site and the driver dashboard).",
      "Turn on push notifications to get alerts on your device: drivers are notified of new bookings, cancellations, chats, and reviews; riders get ride confirmations, cancellations, refunds, and a heads-up before pickup.",
    ],
  },
  {
    version: "0.70.2",
    date: "2026-07-05",
    title: "Faster first paint",
    changes: [
      "The analytics pixel now loads only after you interact with the page, so the homepage's main headline and photo appear faster on slow connections. Tracking is unchanged.",
    ],
  },
  {
    version: "0.70.1",
    date: "2026-07-05",
    title: "Even faster pages",
    changes: [
      "The homepage and route pages load their main photo sooner and ship less JavaScript up front (the chat assistant now loads on demand), so pages feel quicker — especially on phones.",
    ],
  },
  {
    version: "0.70.0",
    date: "2026-07-05",
    title: "Fair quotes for every town + a much faster site",
    changes: [
      "Fixed a pricing gap: rides from towns outside our named zones (like Longmont) were quoting the Denver-core flat rate no matter the distance. The flat rate is now a floor — long trips price by actual distance, and Longmont/Niwot officially ride the Boulder rate.",
      "The site loads much faster, especially on phones: hero photos are now modern WebP (up to 5x smaller), analytics scripts load after the page, and images cache for a month.",
    ],
  },
  {
    version: "0.69.1",
    date: "2026-07-05",
    title: "Blog polish",
    changes: [
      "Hardened the blog widget so browsing back and forward around the site after visiting the blog never affects other pages.",
    ],
  },
  {
    version: "0.69.0",
    date: "2026-07-05",
    title: "Blog",
    changes: [
      "Black Volt Mobility now has a blog at /blog — SEO articles about private luxury EV transfers in Denver, DEN airport runs, and Colorado mountain trips.",
      "You can reach it from Blog in the top navigation and in the footer, in English and Spanish.",
    ],
  },
  {
    version: "0.68.0",
    date: "2026-07-05",
    title: "The notification bell works",
    changes: [
      "The bell in your dashboard header is now live: it shows a count of unread notifications and a panel of recent activity.",
      "You're notified about new rides, cancellations, chats that need a person, new messages, new reviews to approve, redeemed discount codes, and failed subscription payments.",
      "Tap any notification to jump straight to it; mark one or all as read. Works on phone (bottom sheet) and desktop (dropdown), in English and Spanish.",
    ],
  },
  {
    version: "0.67.1",
    date: "2026-07-05",
    title: "Joules speaks your language",
    changes: [
      "Joules now greets you in the language your site is set to — Spanish if you're browsing in Spanish, English if in English — instead of always opening in English.",
      "If you switch languages mid-conversation, Joules follows: it replies in whatever language you just wrote in.",
    ],
  },
  {
    version: "0.67.0",
    date: "2026-07-04",
    title: "Meet Joules — your real AI assistant",
    changes: [
      "The site assistant is now Joules, a real AI that answers questions about fares, coverage, and how the service works — with live pricing straight from the dashboard.",
      "Signed-in passengers can ask Joules about their own upcoming rides (status, pickup time, driver contact once assigned). Sign in with Google to start chatting.",
      "Joules hands off to a human when you ask — it emails Ender your conversation so he can follow up.",
      "Conversations are saved: the owner reviews every chat in the dashboard Inbox, with a badge on the ones that need a person.",
      "Bilingual: Joules replies in English or Spanish to match you.",
    ],
  },
  {
    version: "0.66.4",
    date: "2026-07-04",
    title: "Live prices everywhere",
    changes: [
      "Every advertised price on the site — homepage route cards, the /rides pages and their FAQs, the booking screen placeholder, event landings, and the chat assistant — now reads the live pricing engine instead of hardcoded numbers, so fare updates reach the whole site within minutes.",
      "The chat assistant no longer quotes an outdated $74 airport fare; it answers with the current flat rate.",
      "Renamed the outer pricing ring (it no longer includes the Denver Tech Center, which now enjoys the core Denver-metro flat rate).",
    ],
  },
  {
    version: "0.66.3",
    date: "2026-07-03",
    title: "More competitive flat-zone pricing",
    changes: [
      "Recalibrated every flat-rate zone against current market prices so a Black Volt ride is priced at or below a comparable premium Uber: Boulder ↔ DEN is now $165 (was $180), Denver ↔ Vail $349 (was $390), Summit County $299 (was $349), Colorado Springs $229 (was $359), Fort Collins $199 (was $280), and Loveland/Greeley $169 (was $249).",
      "Centennial, DTC/Greenwood Village, Lone Tree, Parker, Broomfield, and Brighton now price at the core Denver metro flat rate of $110 to DEN — previously they quoted $140–$165.",
      "Fixed addresses on the Aurora/Centennial border (including our home base) quoting the outer-ring price instead of the $110 metro rate.",
    ],
  },
  {
    version: "0.66.2",
    date: "2026-07-03",
    title: "Accurate route prices across the site",
    changes: [
      "Synced every quoted price shown on the homepage, route pages, and the booking screen to the live pricing engine, so the fare you see always matches the fare you pay. The Denver metro / DEN airport flat rate is $110, with per-distance pricing for outer-metro and mountain transfers.",
      "Fixed stale example fares on the Boulder, Vail, Breckenridge, Aspen, DTC, and Red Rocks route pages that were still quoting old numbers.",
    ],
  },
  {
    version: "0.66.1",
    date: "2026-07-03",
    title: "Ad measurement (Meta Pixel + Conversions API)",
    changes: [
      "Added Meta Pixel and the server-side Conversions API so Instagram/Facebook ads can optimize for real bookings, not just clicks. Booking value is reported on quote view, payment start, and confirmation, with browser and server events deduplicated.",
      "Customer contact details are hashed (SHA-256) before being sent for ad matching; no raw email or phone leaves the server. Measurement stays off until an ad account pixel is configured, and only the owner's bookings are reported.",
    ],
  },
  {
    version: "0.66.0",
    date: "2026-07-02",
    title: "Event reservations: prepaid by card",
    changes: [
      "Event and concert rides (one-way and round trip) are now charged in full at booking by card — securing the reservation and avoiding expiring card holds. Everyday rides are unchanged.",
      "Cancellation policy for events: full refund if you cancel 72h or more before pickup, 50% refund within 72h. The policy is shown at checkout.",
    ],
  },
  {
    version: "0.65.2",
    date: "2026-07-02",
    title: "Distance-tiered metro pricing for events",
    changes: [
      "Denver metro is now split into distance tiers so farther premium suburbs pay a fairer rate: close-in stays the base price, the outer ring / DTC (Greenwood Village, Highlands Ranch, Lone Tree, Golden) steps up, and the far ring (Castle Pines, Castle Rock, Parker) is highest — while Boulder keeps its own rate.",
    ],
  },
  {
    version: "0.65.1",
    date: "2026-07-02",
    title: "Event pricing calibration (real operator data)",
    changes: [
      "Round-trip wait pricing tuned against real concert-transport rates so event round trips land competitively (e.g. Boulder → Empower ≈ $500, matching the market).",
      "The Uber Black comparison used in Research now reflects real Denver rates on long premium routes, so the tool no longer under-prices high-value far origins like Boulder.",
    ],
  },
  {
    version: "0.65.0",
    date: "2026-07-02",
    title: "Event pricing: fees, round trips & Uber research",
    changes: [
      "Each event now has its own pricing controls in the dashboard: an event fee, a night fee (auto-applied when the show lets out late), a per-hour wait fee and expected show length. The system suggests a round-trip total you can edit.",
      "Customers can book a round trip in one prepaid checkout — we drive them to the show and pick them up after. Event, night and wait fees apply automatically to any ride to the venue, from any booking channel.",
      "Event pages now show \"One-way from $X · Round trip $Y\" and a dedicated round-trip booking button.",
      "New \"Research prices\" tool compares our fare against Uber Black / Black SUV from affluent Denver origins (Boulder, Cherry Hills, DTC and more) and recommends which areas to target ads on — keeping us competitively priced.",
    ],
  },
  {
    version: "0.64.1",
    date: "2026-07-01",
    title: "Featured events: hardening & fixes",
    changes: [
      "Event pages now keep the \"book your ride home\" button live during and just after the show (it was disappearing the moment the show started).",
      "Event dates in the AI copy and social posts now use Denver time (evening shows were showing the next day).",
      "The event price shown always matches the live Denver-metro fare, and the daily scanner is faster and more reliable (no duplicate events, no rare failure).",
    ],
  },
  {
    version: "0.64.0",
    date: "2026-07-01",
    title: "Featured events: concert & big-event ride pages",
    changes: [
      "New Events section in the dashboard: a daily scanner surfaces big Denver events (Empower Field, Red Rocks, Ball Arena, Coors Field, Fiddler's Green and any large metro show), ranked by date and distance from your base.",
      "Approve an event and its public page goes live instantly at /events/… with artist info, the best drop-off spots before the show, pickup spots after, nearby bars & restaurants, and a flat-$120 booking button — plus two ready-to-review social posts (a video and a photo).",
      "Home page now shows an \"Upcoming events\" strip linking to each event page.",
      "Instagram and TikTok icons added to the public site footer.",
    ],
  },
  {
    version: "0.63.2",
    date: "2026-07-01",
    title: "TikTok: fit non-vertical photos so they publish",
    changes: [
      "Photos that aren't 9:16 now publish to TikTok — they're automatically fitted onto a vertical frame (with a soft blurred background, nothing cropped) just for TikTok, while Instagram keeps your original photo.",
    ],
  },
  {
    version: "0.63.1",
    date: "2026-07-01",
    title: "Social: retry a network on already-published posts",
    changes: [
      "A post that already went live on one network but never made it to another connected one (e.g. Instagram done, TikTok pending) now shows a \"Publish remaining\" button to send it to the missing network — no need to recreate the post.",
    ],
  },
  {
    version: "0.63.0",
    date: "2026-07-01",
    title: "Social: retry a post on the platforms that failed",
    changes: [
      "When a post publishes to some networks but not all, it now shows \"Partly published\" with which networks are done and which are pending, plus a \"Publish remaining\" button that retries only the ones that didn't go through — no duplicate posts.",
    ],
  },
  {
    version: "0.62.5",
    date: "2026-07-01",
    title: "Publishing: no duplicate posts on retry",
    changes: [
      "Re-publishing a post now only fills in the platforms that haven't posted yet — it no longer re-posts to a network it already published to.",
    ],
  },
  {
    version: "0.62.4",
    date: "2026-07-01",
    title: "Fix: image posts to TikTok",
    changes: [
      "Fixed image posts not publishing to TikTok — large uploaded photos are now automatically resized to TikTok's supported size so they post successfully.",
    ],
  },
  {
    version: "0.62.3",
    date: "2026-07-01",
    title: "Fix: publishing image posts to Instagram",
    changes: [
      "Fixed \"Publish now\" appearing to do nothing on image posts — Instagram was rejecting them for a missing required field; image posts now publish to Instagram correctly.",
    ],
  },
  {
    version: "0.62.2",
    date: "2026-07-01",
    title: "Fix: publishing AI image posts",
    changes: [
      "Fixed image posts failing when published — they're now sent to Instagram/Facebook/TikTok as a photo post instead of a video (Buffer was rejecting the image as \"not a video\").",
    ],
  },
  {
    version: "0.62.1",
    date: "2026-07-01",
    title: "Fix: AI-generated image posts",
    changes: [
      "Fixed AI-generated image posts landing as FAILED — the finished image is now saved correctly instead of being rejected as \"not a video\".",
    ],
  },
  {
    version: "0.62.0",
    date: "2026-07-01",
    title: "Social: AI-generated image posts",
    changes: [
      "Photo posts now have a \"My photo\" / \"AI image\" choice — pick AI image and the post's image is generated for you from your topic (Kling text→image), no upload needed.",
      "AI images render in about a minute and land as a draft pending your approval, just like video posts.",
    ],
  },
  {
    version: "0.61.0",
    date: "2026-06-30",
    title: "Social: photo OR video posts + smarter daily auto-posts",
    changes: [
      "Generate a post now has a Video / Photo toggle — a photo post uses your uploaded image directly (AI writes the caption & hashtags, no video render).",
      "Daily auto-posts can create photo posts too (Settings → Social auto-posts: Video / Photo / Mixed); photo days pull from your uploaded photo library and fall back to video if it's empty.",
      "Daily auto-posts are now smarter: they pick the topic from the route/campaign that actually converts to bookings, plus the season's demand, and always end with a call to book — you still approve before anything publishes.",
    ],
  },
  {
    version: "0.60.1",
    date: "2026-06-30",
    title: "Popular routes: teaser prices now match the flat zones",
    changes: [
      "Updated the \"from\" prices on the home Popular routes cards and the route landing pages to match the new flat-rate zones (Aurora/Cherry Creek/DTC/Red Rocks → DEN $120, Boulder → DEN $190, Denver → Vail $390, Breckenridge $349, Aspen $790).",
    ],
  },
  {
    version: "0.60.0",
    date: "2026-06-30",
    title: "Flat-rate zones: fixed prices for Denver metro, Boulder, the mountains, COS & N. Colorado",
    changes: [
      "Rides to/from named zones now charge a fixed flat price (Aspen $790, Vail $390, Summit $349, Colorado Springs $359, Fort Collins $280, Loveland/Greeley $249, Boulder $190, Denver metro & DEN airport $120).",
      "A zone applies when either the pickup or the dropoff is in it; anything outside all zones is still metered by distance and time.",
      "Flat zone prices ignore peak surge; extra stops, group surcharge and discount codes still apply.",
      "Each driver can adjust their own zone prices from the dashboard Rates screen.",
    ],
  },
  {
    version: "0.59.0",
    date: "2026-06-30",
    title: "Smart reservation: batch multiple requests + recoverable scans",
    changes: [
      "Add ride → Smart now reads several clients' requests at once: drop up to 6 screenshots and it groups them by client into separate draft reservations.",
      "Review them in a queue and create them individually or all at once — nothing is saved until you confirm.",
      "Failed scans are recoverable: a clear 'Start over' button plus messages when a file isn't an image or you hit the screenshot limit (no more silent failures).",
    ],
  },
  {
    version: "0.58.0",
    date: "2026-06-29",
    title: "Reviews: centralized moderation across all drivers",
    changes: [
      "The owner now sees and approves reviews for every driver from one panel, each tagged with the driver it belongs to.",
      "New driver filter to focus the panel on a single driver's reviews.",
      "Reviews left on a driver's public profile are now attributed to that driver (correct ownership).",
    ],
  },
  {
    version: "0.57.0",
    date: "2026-06-29",
    title: "Insights: visual booking funnel + conversion by campaign",
    changes: [
      "The booking funnel is now an interactive visual chart (started → reviewed → paid → confirmed) — hover any step to see its conversion and drop-off.",
      "New campaign selector + table: see conversion (starts → confirmed) per UTM campaign, attributed by session. Pick a campaign to view its own funnel.",
      "Funnel now counts distinct sessions (real conversion) instead of raw clicks.",
    ],
  },
  {
    version: "0.56.0",
    date: "2026-06-29",
    title: "Insights: interactive charts + accurate time metrics",
    changes: [
      "The Insights dashboard now has an interactive traffic chart (visitors + pageviews over time) with hover details, and a device-mix donut.",
      "Fixed inflated time-on-page/session averages: an idle tab left open no longer skews the numbers (capped at 30 minutes).",
    ],
  },
  {
    version: "0.55.0",
    date: "2026-06-28",
    title: "Automatic review requests after each ride",
    changes: [
      "Black Volt can automatically email past riders a few hours after their ride, inviting them to leave a review — no manual step needed.",
      "Off by default: turn it on in Settings → Auto review requests and choose how many hours after the ride to send (default 3).",
    ],
  },
  {
    version: "0.54.0",
    date: "2026-06-28",
    title: "Customer reviews: collect, moderate & request",
    changes: [
      "Riders can now leave a star rating + review — from a completed trip, a profile link, or a request you send. Reviews stay hidden until you approve them.",
      "New admin Reviews section: approve/reject, toggle which reviews show on the home page, feature the best ones, and reply.",
      "Request a review from any past customer by email, text message, or a copy-paste link.",
      "Approved reviews appear on the home page, route pages, and your driver profile.",
    ],
  },
  {
    version: "0.53.0",
    date: "2026-06-28",
    title: "Route pages: premium hero, real route map & trust signals",
    changes: [
      "Each route page now opens with a luxury-vehicle hero image and shows a real, brand-styled map of the actual drive — so visitors instantly see the route and the experience.",
      "Added a trust strip (owner-driven, fully insured, 100% electric, flat upfront pricing, flight-aware, private) to build confidence before booking.",
    ],
  },
  {
    version: "0.52.1",
    date: "2026-06-27",
    title: "Route pages discoverable from the home page & footer",
    changes: [
      "Added a 'Popular routes' section to the home page and route links in the footer, so visitors (especially on mobile) can find the new route pages — and it strengthens internal SEO linking.",
      "Updated the footer to show the full service area (Denver metro · DEN · Vail/Breck/Aspen).",
    ],
  },
  {
    version: "0.52.0",
    date: "2026-06-27",
    title: "SEO route landing pages for organic traffic",
    changes: [
      "New dedicated pages for high-intent local searches (Aurora→DEN, Cherry Creek→DEN, DTC corporate, Boulder→DEN, Red Rocks concert rides, and Denver→Vail/Breckenridge/Aspen) — each with a real example fare and a one-tap link to an instant quote with the trip prefilled.",
      "Added the SEO foundation Google needs: sitemap.xml, robots.txt, and structured data (LocalBusiness, Service & FAQ) so these pages get discovered and can earn rich results.",
    ],
  },
  {
    version: "0.51.0",
    date: "2026-06-27",
    title: "Service area: full Denver metro + mountain resort transfers",
    changes: [
      "The site and your AI social posts now state the full service area: door-to-door across the Denver metro (including Boulder), DEN airport transfers both ways, and luxury mountain transfers to Vail, Breckenridge & Aspen.",
      "Added a coverage line on the booking page so riders see exactly where you go.",
    ],
  },
  {
    version: "0.50.0",
    date: "2026-06-27",
    title: "Booking funnel: show price first + reliable conversion tracking",
    changes: [
      "Visitors now see their fare instantly — no account required to get a price. You only sign in to actually book. This removes the biggest drop-off before paying for traffic.",
      "The dashboard booking funnel is now measured reliably: each step counts once per visitor (no inflation from reloads), 'reviewed route' means the rider actually saw a price, and failed payments are now tracked so you can see where riders drop.",
    ],
  },
  {
    version: "0.49.0",
    date: "2026-06-27",
    title: "Social posts: general luxury-EV focus + reference photo matching",
    changes: [
      "Generated social posts no longer force the specific car model. They now open with an attention-grabbing fact about luxury electric vehicles and only mention booking a luxury EV for door-to-door rides and DEN airport transfers at the end.",
      "When you upload a reference photo, the video now keeps every vehicle shot consistent with your car — the uploaded photo anchors the ad (multiple motion shots) and any AI-generated shots are described to match it, instead of showing unrelated cars.",
    ],
  },
  {
    version: "0.48.1",
    date: "2026-06-26",
    title: "Driver profile: working social links, correct booking, vCard photo",
    changes: [
      "Fixed the driver profile Instagram and website links — they now show as clean tappable buttons (with the Instagram and web icons) and open the right page even if the full URL was pasted.",
      "\"Book a ride\" and the shared profile link / QR now always open the public booking site (blackvoltmobility.com), carrying the driver so the price is correct.",
      "Driver profile URL is now personalized (e.g. /d/ender-ocando); old links keep working via redirect.",
      "\"Save contact\" now downloads a complete contact card including the driver's photo.",
    ],
  },
  {
    version: "0.48.0",
    date: "2026-06-26",
    title: "Mandatory client/driver agreement signing",
    changes: [
      "Passengers must read and accept the client terms before booking; drivers must read and electronically sign the driver agreement (typed full legal name) before using the dashboard.",
      "The agreement appears as a full-screen step you can't skip, available in English and Spanish.",
    ],
  },
  {
    version: "0.47.1",
    date: "2026-06-26",
    title: "Social video voice no longer reads hashtags",
    changes: [
      "Fixed: the generated social video voiceover was reading hashtags aloud. Hashtags are now stripped from the spoken script (kept only in the post caption).",
    ],
  },
  {
    version: "0.47.0",
    date: "2026-06-26",
    title: "Cancel a ride from the app + driver refund choice",
    changes: [
      "You can now cancel an upcoming ride yourself from My Trips, any time before your driver is on the way.",
      "Cancel 24+ hours ahead and you're refunded in full, automatically.",
      "Cancel within 24 hours and your driver decides: a full refund or a 20% / 30% cancellation fee.",
      "Your assigned driver's name and contact now appear on every confirmed trip, so Call and Text always work.",
      "Drivers are emailed when a new ride is booked and when a ride is cancelled.",
    ],
  },
  {
    version: "0.46.0",
    date: "2026-06-26",
    title: "Pay your driver at drop-off + real trips with call & text",
    changes: [
      "At payment you can now choose 'Pay at drop-off': confirm your ride now and pay your driver (cash or card) when you arrive — no online charge.",
      "Your ride is only confirmed once you finish the payment step, so an unfinished booking no longer lands on your driver's calendar.",
      "My Trips now shows your real upcoming and past rides instead of sample data.",
      "Call or text your assigned driver in one tap from a trip — it opens your phone's dialer or messages app.",
    ],
  },
  {
    version: "0.45.1",
    date: "2026-06-26",
    title: "Discount codes: redeem on payment & owner-driver pricing",
    changes: [
      "A discount code is now counted as used only when payment succeeds — abandoned bookings no longer waste a code's uses.",
      "Rides booked with a driver's code are now priced using that driver's own rates.",
    ],
  },
  {
    version: "0.45.0",
    date: "2026-06-25",
    title: "Discount codes on booking, driver codes module & admin campaigns",
    changes: [
      "Passengers can now apply a discount code at booking — the fare is reduced in real time before payment.",
      "Reservation-only booking: on-demand Now rides have been removed; all bookings are scheduled.",
      "Drivers have a new Discount Codes panel in the dashboard to create, toggle and delete promo codes for their clients (capped at 50%).",
      "Admins can now create multi-driver campaigns: one form generates a unique code per selected driver, with an All Drivers shortcut.",
    ],
  },
  {
    version: "0.44.0",
    date: "2026-06-25",
    title: "Social posts now cross-post to TikTok",
    changes: [
      "Your generated social videos now publish to TikTok automatically alongside Instagram and Facebook, through your connected Buffer account.",
      "TikTok is skipped safely when its channel isn’t connected, so nothing breaks for accounts without it.",
    ],
  },
  {
    version: "0.43.0",
    date: "2026-06-25",
    title: "Ride preferences — tell your driver how you like to ride",
    changes: [
      "New “Ride preferences” panel in your account: set your defaults for conversation, temperature, music, luggage help, pets/service animals, and a note for your driver (e.g. allergies).",
      "Set preferences right when you sign up, in an optional section of the profile form.",
      "Adjust your preferences for any single ride at booking — change them for this trip or keep your defaults.",
      "Your driver now sees your preferences on the ride so your arrival feels just right.",
    ],
  },
  {
    version: "0.42.2",
    date: "2026-06-25",
    title: "Driver accounts no longer get stuck on the customer profile screen",
    changes: [
      "If you sign into the customer site with a driver account, we now take you straight to your dashboard instead of showing a customer profile form that couldn't be saved.",
    ],
  },
  {
    version: "0.42.1",
    date: "2026-06-25",
    title: "Account fixes: address autocomplete in dialogs + visible default address",
    changes: [
      "Fixed address autocomplete inside the “Add address” and “Complete your profile” dialogs — suggestions were being cut off by the dialog and are now fully visible and selectable.",
      "Your default address now shows on your account, so updating it in “Complete your profile” is clearly reflected.",
    ],
  },
  {
    version: "0.42.0",
    date: "2026-06-24",
    title: "Your account, for real: saved addresses, honest payment, saved preferences",
    changes: [
      "Saved addresses now actually work — add, edit, delete and pick a default, with the same address autocomplete as the booking page.",
      "Your language, SMS and email preferences now stick across visits instead of resetting.",
      "The payment section now honestly explains how it works: you pay per ride at booking with Square — no card is stored on file.",
      "Works the same on phone, tablet and computer.",
    ],
  },
  {
    version: "0.41.0",
    date: "2026-06-24",
    title: "Easy date & time picker — on phone and computer",
    changes: [
      "Picking a date and pickup time is now fully tap-and-click — a branded calendar and time selector with quick shortcuts (Today, Tomorrow, common times). No more typing, especially on your phone.",
      "Clients can finally schedule a ride for later: choosing \"Schedule\" on the booking page now shows the date and time picker (it previously did nothing).",
      "Works the same on phone, tablet and computer.",
    ],
  },
  {
    version: "0.40.1",
    date: "2026-06-24",
    title: "Reliable date & time when adding a ride",
    changes: [
      "Adding a ride now uses proper date and time pickers, so the scheduled time is always saved correctly (in any language).",
      "This fixes rides being created without a time — which silently kept them off your Google Calendar.",
      "If a date or time is missing, the form now tells you instead of creating a ride with no schedule.",
    ],
  },
  {
    version: "0.40.0",
    date: "2026-06-23",
    title: "Connect your own Google Calendar",
    changes: [
      "Team members can now connect their own Google Calendar from Settings, so the rides you create sync to YOUR calendar — not the admin's.",
      "Admins keep using the shared Black Volt calendar, exactly as before.",
      "Until a member connects their calendar, their rides simply don't sync anywhere — no more events landing on the wrong calendar.",
      "Your Google permission is limited to managing calendar events, and your token is stored encrypted. Disconnect any time from Settings.",
    ],
  },
  {
    version: "0.39.0",
    date: "2026-06-23",
    title: "Finish your profile right after you sign in",
    changes: [
      "New riders are now asked for the details Google can't share — your phone, and your name if it's missing — right after you sign in, so your driver can always reach you before your first ride.",
      "Your phone is saved in a clean, standard format (US numbers and international both work).",
      "Add an optional default address, with the same address autocomplete used on the booking form, to speed up future pickups.",
      "You can now edit your own profile from the Account page.",
    ],
  },
  {
    version: "0.38.0",
    date: "2026-06-21",
    title: "Social: adjust a post's images too — by feedback and by hand",
    changes: [
      "Rejecting a post with a reason now also steers the images: your reason (and your past lessons) guide the AI-generated scenes, so when you re-render the visuals reflect what you asked for — not just the text.",
      "New 'Edit images' on a post: add or remove your own uploaded images right on the card. Saving changes sends the post back to draft so you can re-render with the new images.",
    ],
  },
  {
    version: "0.37.0",
    date: "2026-06-21",
    title: "Social: reject a post with a reason — it fixes itself and learns",
    changes: [
      "When you reject a proposed post you can now write why. The system instantly rewrites the script, caption and hashtags to fix exactly what you flagged and leaves it as a corrected draft, ready to re-render.",
      "It also remembers your feedback: every reason you give becomes a brand lesson that's applied to all future posts, so the AI stops repeating the same mistakes over time.",
      "Rejecting without a note still just sends the post back to draft, like before.",
    ],
  },
  {
    version: "0.36.0",
    date: "2026-06-21",
    title: "Social: live progress bar while your video renders",
    changes: [
      "When you render a Social post you now see a real progress bar that moves as the video is built — recording the voiceover, animating your photos, creating the scenes, assembling and finishing — instead of just a 'Rendering' tag.",
      "The queue refreshes itself while a post is rendering, so the finished video appears on its own the moment it's ready — no need to reload the page.",
    ],
  },
  {
    version: "0.35.0",
    date: "2026-06-21",
    title: "Social: add your own images to posts + generate from one image",
    changes: [
      "In 'Generate a post' you can now attach your own photos — a vehicle, a backdrop — and they're animated right into the video (smooth motion when AI-video credits allow, an elegant Ken Burns zoom otherwise).",
      "New 'Generate from an image' button: upload one photo and the AI looks at it, writes the whole post around it, and builds the video from it.",
      "Every post is now framed for the real service: premium rides across all of Denver and both-way airport transfers (anywhere in Denver → DEN, and DEN → anywhere in Denver).",
    ],
  },
  {
    version: "0.34.0",
    date: "2026-06-20",
    title: "Social: publish for real via Buffer",
    changes: [
      "Connect your Instagram, Facebook and TikTok through your Buffer account: open Social → Accounts and tap 'Sync from Buffer' to see your connected channels.",
      "Approved posts now publish for real through Buffer (Instagram goes out as a Reel) — Buffer handles the platform logins and posting, so there's nothing to set up with Meta or TikTok.",
      "If a channel isn't connected yet, a 'Connect in Buffer' link takes you straight there. Posts still wait for your approval before anything goes live.",
    ],
  },
  {
    version: "0.33.0",
    date: "2026-06-18",
    title: "Social: real Black Volt video ads",
    changes: [
      "Render now makes a real Black Volt ad: cinematic AI visuals of a luxury electric SUV (Denver / airport / night), your own 'BLACK VOLT' mark, an elegant end card with the tagline, and a voiceover in the post's language (English or Spanish) — no more generic clip or mixed-language audio.",
      "The video is built from AI prompts written for your brand, so each post gets on-brand, premium footage. (Real motion video clips need the AI-video credits topped up; meanwhile it uses crisp AI images with cinematic motion.)",
      "Every video is web-safe, so it plays everywhere and downloads cleanly.",
    ],
  },
  {
    version: "0.32.1",
    date: "2026-06-18",
    title: "Social: video render is now live",
    changes: [
      "Render is switched on in production: tapping 'Render video' on a Social post now builds a real video file and drops it into your queue to preview and approve — over a secure, signed channel.",
      "For now it produces a branded Black Volt clip; wiring the full AI-video engine (Hailuo voiceover + clips) is the next step.",
    ],
  },
  {
    version: "0.32.0",
    date: "2026-06-17",
    title: "Social: real AI video render + admin-only",
    changes: [
      "The Social module now produces a real video: when you render a post, it's built by the video engine and the finished clip lands right in your content queue, ready to preview and approve (no more placeholder).",
      "The 'Social' section is now admin-only — only you (and any admins you add) can see and manage it; regular drivers don't see it at all.",
      "Behind the scenes: the rendered video is delivered over a signed, tamper-proof channel and validated before it's saved.",
    ],
  },
  {
    version: "0.31.0",
    date: "2026-06-17",
    title: "Social Media — let AI run your socials, you approve",
    changes: [
      "New 'Social' tab: tell the AI a topic and it writes a ready-to-post video script, caption and hashtags from your brand (the EV9, premium arrival, your city) — in English or Spanish. Nothing publishes until you approve it.",
      "Content queue: every post moves Draft → Render → Approve → Publish, with one-tap Approve / Reject / Publish and a schedule option. You're always in control before anything goes out.",
      "Social inbox: comments and DMs land in one place and the AI drafts a friendly, on-brand reply you can edit and send. Replies are drafted safely — a comment can never trick the AI into going off-script.",
      "Connect Instagram, Facebook and TikTok (setup coming): until then everything runs in a safe simulated mode so you can try the whole flow end-to-end.",
      "Works great on phone, tablet and desktop — the Social tab is in both the sidebar and the mobile menu.",
    ],
  },
  {
    version: "0.30.0",
    date: "2026-06-16",
    title: "My Stats: an AI coach + visible 'Revenue over time' bars",
    changes: [
      "Your Stats tab now has a coach: one motivating, specific nudge — talk to N people a day for a ~Z% shot at landing new private clients and the revenue that brings. The numbers come straight from your real funnel, so they're always honest; the AI just puts them into friendly words (and it still works if the AI is offline). Tap Regenerate for a fresh take.",
      "Fixed the 'Revenue over time' and 'Conversations over time' charts so the daily bars are clearly visible on past days too (they were nearly invisible before), and each chart now shows its total next to the title.",
    ],
  },
  {
    version: "0.29.1",
    date: "2026-06-16",
    title: "Week chart: visible bars on past weeks + totals in the picker",
    changes: [
      "Fixed the 'This week' chart so the daily bars are clearly visible on past weeks too (they were nearly invisible before).",
      "The week picker now shows each week's total next to its dates, so you can compare weeks at a glance.",
    ],
  },
  {
    version: "0.29.0",
    date: "2026-06-16",
    title: "Browse past weeks on the dashboard chart",
    changes: [
      "The 'This week' chart on the Dashboard can now look back at any week: use the ‹ › arrows or tap the date range to pick a week from the dropdown.",
      "Each week shows its own daily bars and total, so you can compare how you're doing week to week.",
      "Works great on phone and tablet — the week picker opens as an easy-to-tap sheet on mobile.",
    ],
  },
  {
    version: "0.28.1",
    date: "2026-06-16",
    title: "My Stats now reachable on mobile",
    changes: [
      "Fixed: the 'My Stats' tab was missing from the phone navigation — it's now in the bottom 'More' menu (it was already in the sidebar on desktop).",
    ],
  },
  {
    version: "0.28.0",
    date: "2026-06-16",
    title: "My Stats — import your Uber/Lyft income with AI",
    changes: [
      "New 'Platform income' panel in My Stats: upload a screenshot of your Uber, Lyft or co-op earnings and the AI reads the trips, earnings and hours for you.",
      "See your platform income vs your private (Black Volt) income side by side — a clear picture of how much more you keep on private rides, and a nudge to grow it.",
      "Review what the AI read before saving, edit anything, and delete old imports anytime. It's context only — it never changes your sales-funnel numbers.",
    ],
  },
  {
    version: "0.27.0",
    date: "2026-06-16",
    title: "My Stats — your growth dashboard + revenue fixes",
    changes: [
      "New 'My Stats' tab: log your daily sales funnel (people you talked to, pitches, contacts) and watch it turn into clients and revenue, with conversion rates, a streak, and trend charts.",
      "Goal calculator: set a weekly/monthly/yearly target ($ or clients) and it tells you how many people to talk to per day — backed by a smoothed statistical model that's honest when you have little data.",
      "Fixed 'Revenue today' and 'Week total': a completed ride now counts as revenue even if you didn't toggle 'paid', and cancelled rides never count.",
      "Fixed 'Rides today' to count every ride you did today (including ad-hoc ones) and exclude cancelled rides.",
      "You can now delete a cancelled ride from its detail view.",
    ],
  },
  {
    version: "0.26.1",
    date: "2026-06-15",
    title: "Settings — Save button always works",
    changes: [
      "The 'Save changes' button on Settings is now always clickable while your profile is loaded — it no longer greys out, so you can always save your edits.",
      "An 'Unsaved changes' tag appears while you're editing, so it's clear when you have changes to save.",
    ],
  },
  {
    version: "0.26.0",
    date: "2026-06-15",
    title: "Your direct phone — for your registered clients",
    changes: [
      "Add your direct phone in Settings → it appears as Call and Text buttons (and in save-to-contacts) on your profile.",
      "Your number is shown only to clients who are signed in — anonymous visitors never see it, keeping it private while still giving real clients a direct line.",
    ],
  },
  {
    version: "0.25.0",
    date: "2026-06-15",
    title: "Your own driver link — share, get clients, keep them",
    changes: [
      "Every driver now has a public link and scannable QR (Settings → Share your link) for Instagram, business cards or flyers.",
      "Anyone who signs up through your link becomes your client for good — their rides and CRM live under you (first come, first keep).",
      "The 'Your Driver' tab now shows each rider their own designated driver, with a real QR, save-to-contacts and copy-link.",
      "To get a price, riders now create a free account first (one-tap Google) — so every lead is captured and credited to the right driver.",
    ],
  },
  {
    version: "0.24.0",
    date: "2026-06-12",
    title: "Team member detail — know everything about each driver",
    changes: [
      "Click any driver in Team to open a detail drawer: their access, subscription, rides, revenue, clients, weekly earnings, 30-day platform usage (sessions, pageviews, booking funnel, devices), recent rides and recent activity.",
      "Manage the driver right from the drawer — activate/deactivate, change role, resend the welcome email, copy the invite, or remove access.",
    ],
  },
  {
    version: "0.23.1",
    date: "2026-06-11",
    title: "Driver subscriptions live — webhook sync fixed",
    changes: [
      "Driver subscriptions are now live at driver.blackvoltmobility.com with the Operator plan ($29/mo or $290/yr).",
      "Fixed the Square webhook so subscription status (paid, past-due, cancelled) syncs reliably — it was reading the wrong signature header and rejecting real events.",
    ],
  },
  {
    version: "0.23.0",
    date: "2026-06-11",
    title: "Driver subscriptions — Operator plan landing + checkout",
    changes: [
      "New driver landing page (driver.blackvoltmobility.com) where other drivers can subscribe to the Operator plan and pay by card with Square.",
      "Choose monthly ($29) or annual ($290, ~2 months free) with a one-tap toggle — the price and plan update together.",
      "Card details go straight to Square and never touch our servers; if Square isn't connected yet the page invites you to contact us instead.",
      "Free plan links to the dashboard sign-up; Growth plan opens a sales email.",
      "Behind the scenes: Square webhooks now keep each subscription in sync as payments succeed, fail, or get cancelled.",
    ],
  },
  {
    version: "0.22.0",
    date: "2026-06-10",
    title: "Team panel upgrade: roles, welcome emails, per-driver activity",
    changes: [
      "Change a teammate's role between admin and driver right from the Team page — with safeguards so you can never lock yourself out (the owner account and the last admin are protected).",
      "When you add a driver, they now get a bilingual welcome email with their sign-in link. You'll see whether it was sent (turn on Resend to send for real; until then it's simulated and just logged).",
      "Each member row now shows their activity at a glance: number of rides, revenue, and when they last signed in.",
      "New 'Copy invite' button puts a ready-to-share welcome message + link on your clipboard, and 'Resend email' re-sends the welcome anytime.",
    ],
  },
  {
    version: "0.21.0",
    date: "2026-06-08",
    title: "Invite drivers: access list + each driver gets their own workspace",
    changes: [
      "New Team section (admin only): add a driver's Google email to grant dashboard access, and toggle them active/inactive anytime — only people on your list can sign in.",
      "When an invited driver signs in with Google the first time, their own private workspace is created automatically — their rides, clients and settings are fully separate from yours.",
      "Deactivating a driver instantly blocks their access without deleting any of their data; reactivating restores it.",
      "Next up: each driver connecting their own Square account to take card payments.",
    ],
  },
  {
    version: "0.20.2",
    date: "2026-06-08",
    title: "Dashboard shows real numbers: revenue, next-pickup countdown, weekly earnings",
    changes: [
      "Revenue today now counts only paid rides scheduled for today — it no longer jumps when you mark an old ride as paid.",
      "Next pickup shows how long until it (e.g. '5d 2h') plus the date, time and client.",
      "The 'This week' chart now runs Monday→Sunday and graphs your real earnings, with the week's total shown above it.",
      "Removed the placeholder '+18% / +2 vs yesterday' figures that weren't real.",
    ],
  },
  {
    version: "0.20.1",
    date: "2026-06-08",
    title: "Fix: the dashboard panel no longer shows old completed rides",
    changes: [
      "When you have no rides today, the dashboard panel now shows your next upcoming rides (and is titled 'Upcoming rides') instead of listing old completed ones.",
      "Days with rides scheduled today are unchanged — the panel shows the full day under 'Today's rides'.",
    ],
  },
  {
    version: "0.20.0",
    date: "2026-06-08",
    title: "Wider client names, smart route prefill, and one-tap Navigate",
    changes: [
      "Rides list: the Client column is now wider so full names fit, and the Route column gives up the space instead of getting covered.",
      "Add ride: picking a client now also prefills the route — pickup from their saved home (or most-used address) and drop-off to their usual airport (DEN by default for a brand-new client). Only fills fields you haven't typed.",
      "Add ride: a Swap button flips pickup ↔ drop-off in one tap — handy for the return trip.",
      "Clients: you can save a Home address on a client's profile; it's used as the default pickup next time.",
      "Rides: a Navigate button (in the list and in the ride detail) opens your maps app with directions to the pickup — no typing the address.",
    ],
  },
  {
    version: "0.19.1",
    date: "2026-06-08",
    title: "Fix: long client names no longer overlap the route",
    changes: [
      "In the rides list and the dashboard, a long client name now truncates with an ellipsis.",
      "It used to spill over and cover the pickup → drop-off route next to it.",
      "Long pickup/drop-off addresses also shorten cleanly instead of crowding the row.",
    ],
  },
  {
    version: "0.19.0",
    date: "2026-06-08",
    title: "Clients are saved automatically + name autocomplete + add/edit/delete",
    changes: [
      "Add ride now saves the client to your CRM automatically — typing a name (or a Smart extraction) creates or links a real client, so they show up in Clients and build up rides + lifetime spend.",
      "The Full name field autocompletes from your saved clients (Manual and Smart) — pick one and it fills the phone + language and links the ride to them.",
      "Clients page: 'Add client' to create one by hand, and delete a client from their profile.",
      "Deleting a client keeps their past rides (the name + phone stay on each ride) — no history or revenue is lost.",
    ],
  },
  {
    version: "0.18.1",
    date: "2026-06-07",
    title: "Dashboard looks like a phone app on any screen",
    changes: [
      "On wide foldables/tablets (e.g. an unfolded Galaxy Z Fold) the dashboard now shows a centered app column instead of stretching edge-to-edge.",
      "Fixed horizontal scrolling on phones — the Add ride form and other 2-column rows now shrink to fit instead of running off the screen.",
      "Normal phones are unchanged (full width); desktop keeps the sidebar.",
    ],
  },
  {
    version: "0.18.0",
    date: "2026-06-07",
    title: "Calendar fixed — pickups post again + real invites",
    changes: [
      "Fixed: new pickups stopped landing on the Google Calendar (adding guests via a service account was rejected by Google).",
      "Pickups post again immediately; with the owner's Google account connected, Margie and Ender now get a real event invitation per pickup.",
      "Reminders are now 2 hours and 1 hour before you leave the house (house→house departure time).",
      "The driver's home (6000 S Fraser St) deadhead is subtracted so the event blocks the full door-to-door time.",
    ],
  },
  {
    version: "0.17.0",
    date: "2026-06-06",
    title: "Overdue rides — confirm the pickup happened",
    changes: [
      "A ride whose pickup time has passed now shows an amber 'Overdue' badge instead of staying 'Upcoming'.",
      "Open it and tap 'Confirm pickup completed' to close it in one step — no need to mark 'en route' first.",
      "If the ride is already paid (e.g. Square captured the payment), it auto-completes — no tap needed.",
      "Overdue rides still appear under the Upcoming filter so nothing gets lost.",
    ],
  },
  {
    version: "0.16.0",
    date: "2026-06-06",
    title: "Manual update + pickup-protocol calendar events",
    changes: [
      "On a saved ride, tap 'Manual update' to edit the details by hand — the same form as Smart update, without screenshots.",
      "Your edits re-quote the fare, warn about a clashing ride, and re-sync the Google Calendar event automatically.",
      "Calendar events now follow the pickup protocol: the title shows the real pickup time and route (🚗 Pickup …).",
      "Each event blocks the full house→house time (drive to pickup + trip + drive home + buffer), reminds 30 and 60 min before, and invites your dispatcher + driver.",
    ],
  },
  {
    version: "0.15.1",
    date: "2026-06-06",
    title: "Fix: 'Your Driver' link no longer 404s",
    changes: [
      "The public 'Your Driver' nav, mobile tab, and landing button now open the real profile.",
      "They pointed at an old demo URL that broke once profiles went live in 0.15.0.",
      "An unknown profile link now shows a friendly page with a 'Book a ride' button.",
    ],
  },
  {
    version: "0.15.0",
    date: "2026-06-05",
    title: "Settings — your brand & public profile, for real",
    changes: [
      "Edit your business profile (name, tagline, bio, vehicle, service area, Instagram, website).",
      "Pick your brand accent color and upload a logo + hero photo.",
      "Set your rating and the year you started — they power your public profile stats.",
      "Your public page at /d/your-slug now shows your real, edited details (not a demo).",
      "See your Square payout status at a glance; SMS/AI-call channels are flagged as coming soon.",
    ],
  },
  {
    version: "0.14.0",
    date: "2026-06-05",
    title: "Client profiles — tap a client to see everything",
    changes: [
      "Tap any client to open their full profile: contact, tier, lifetime spend, member since.",
      "Edit the client's name, phone, email and preferred language inline.",
      "See their complete ride history; tap a ride to open it.",
      "One tap to start a new ride pre-filled for that client.",
    ],
  },
  {
    version: "0.13.1",
    date: "2026-06-04",
    title: "Smart extraction reads the right pickup date",
    changes: [
      "AI now anchors to today's date — 'today/tomorrow/this Friday' resolve correctly.",
      "It takes the customer's pickup date, not a flight itinerary's departure date.",
    ],
  },
  {
    version: "0.13.0",
    date: "2026-06-04",
    title: "Reservations that silently failed now actually save",
    changes: [
      "Fixed: a ride could show 'created' but never save when a field was too long.",
      "Flight number accepts full airline names; language accepts any wording (→ EN/ES).",
      "If creating a reservation fails, you now see exactly why instead of a false success.",
      "Cancelled rides no longer clutter the calendar.",
    ],
  },
  {
    version: "0.12.2",
    date: "2026-06-04",
    title: "Smart extraction: survive transient network blips",
    changes: [
      "A flaky TLS/network glitch during AI reading no longer fails the whole extraction.",
      "Each screenshot retries on a transient error and degrades gracefully if it can't recover.",
    ],
  },
  {
    version: "0.12.1",
    date: "2026-06-04",
    title: "Smart extraction: reliable on any device + clear errors",
    changes: [
      "Screenshots are normalized in-browser (downscaled + re-encoded) so it works from Android, iPhone, Mac or Linux.",
      "Real reasons now show instead of a silent '0 found': unsupported format, too large, or service down.",
      "If AI reads nothing, it says so and lets you fill the form by hand.",
    ],
  },
  {
    version: "0.12.0",
    date: "2026-06-04",
    title: "Smart update — change a ride from screenshots",
    changes: [
      "On a ride, tap 'Smart update' and drop the client's change-of-plans screenshots.",
      "AI reads the new details; you review the diff and the fare re-quotes itself.",
      "Warns if the new time clashes with another ride — apply anyway if you choose.",
      "After applying, copy or send the change-confirmation message (SMS/email/call).",
    ],
  },
  {
    version: "0.11.1",
    date: "2026-06-04",
    title: "Smart reservation — MiniMax Coding Plan vision",
    changes: [
      "Smart extraction now supports the MiniMax Coding Plan (subscription) vision API.",
      "Each screenshot is read and merged into one reservation; newer images win.",
      "Switch provider with SMART_VISION_PROVIDER (coding plan or pay-as-you-go M3).",
    ],
  },
  {
    version: "0.11.0",
    date: "2026-06-04",
    title: "Smart reservation — real AI from multiple screenshots",
    changes: [
      "Smart 'Add reservation' now reads screenshots with real AI (MiniMax-M3 vision).",
      "Drop, paste or upload several screenshots — they merge into one reservation.",
      "Remove or add screenshots before extracting; up to 5 at once.",
      "Falls back to a demo sample until the vision key is set on the server.",
    ],
  },
  {
    version: "0.10.0",
    date: "2026-06-02",
    title: "Google Calendar sync for scheduled rides",
    changes: [
      "Scheduled rides push to the Black Volt Google Calendar automatically.",
      "Cancelling a ride removes its calendar event.",
      "Add ride now saves a real date + time so rides land on the calendar.",
      "See docs/setup-google-calendar.md to connect your calendar.",
    ],
  },
  {
    version: "0.9.0",
    date: "2026-06-02",
    title: "Real history import + payment methods + Square auto-sync",
    changes: [
      "Imported real clients + trips + charges from Square history.",
      "Each ride has a payment method (default cash) and a paid flag.",
      "Square payments auto-sync in; you can switch a ride to Venmo/Zelle/cash.",
      "Revenue and client spend now count every payment method, not just card.",
    ],
  },
  {
    version: "0.8.0",
    date: "2026-06-02",
    title: "Phase 4 — Driver dashboard on real data",
    changes: [
      "Overview KPIs, rides, calendar and clients now come from your real data.",
      "Tap a ride to see full detail and change status (en route / complete / cancel).",
      "Capture the Square payment right from the ride detail.",
      "Clients CRM with real ride count, lifetime spend and tier.",
    ],
  },
  {
    version: "0.7.0",
    date: "2026-06-01",
    title: "Phase 3 — Square payments",
    changes: [
      "Real card payments on the booking flow via the Square Web Payments SDK.",
      "Authorize at booking → capture on completion → refund (Payments API).",
      "Card data never touches our servers; sandbox by default (test card 4111…).",
      "Simulated fallback keeps the flow working without Square configured.",
    ],
  },
  {
    version: "0.6.0",
    date: "2026-06-01",
    title: "Usage analytics (first-party Insights)",
    changes: [
      "Privacy-first event tracking: pageviews, time-on-page, booking funnel, sign-ins.",
      "New driver 'Insights' page: visitors, sessions, top pages, funnel, sources, devices, countries.",
      "Pseudonymous (random visitor id, no raw IP); country via Cloudflare.",
      "All data stays in our own database — no third-party trackers.",
    ],
  },
  {
    version: "0.5.1",
    date: "2026-06-01",
    title: "Address autocomplete + live fares in booking",
    changes: [
      "Pickup/drop-off fields autocomplete real addresses (Google Places).",
      "Booking 'Review route' now shows live distance, ETA and fare from /quote.",
      "Driver dashboard 'Add ride' gets the same address autocomplete.",
    ],
  },
  {
    version: "0.5.0",
    date: "2026-05-31",
    title: "Phase 2 — Booking core (route + pricing engine)",
    changes: [
      "Ride + RateConfig models (multi-tenant); fare engine + Google Maps adapter.",
      "Quote API prices any trip from route distance/duration + per-tenant rates.",
      "Maps simulated by default (deterministic) — one key flips it live.",
      "Rates editor now loads + saves the live fare engine.",
      "Add ride suggests a live quote and persists the reservation.",
      "See docs/setup-google-maps.md.",
    ],
  },
  {
    version: "0.4.2",
    date: "2026-05-31",
    title: "Google sign-in for the driver dashboard",
    changes: [
      "Driver /login adds a Google button (allow-listed emails → owner session).",
      "Non-authorized Google accounts are rejected with a clear message.",
      "Password login kept as the master fallback.",
    ],
  },
  {
    version: "0.4.1",
    date: "2026-05-31",
    title: "Passenger Google sign-in (real GIS)",
    changes: [
      "Portal sign-in renders the real Google button when configured.",
      "Real session reflected in the header; sign-out clears the cookie.",
      "Dormant (demo button) until NEXT_PUBLIC_GOOGLE_CLIENT_ID is set.",
      "See docs/setup-google-signin.md.",
    ],
  },
  {
    version: "0.4.0",
    date: "2026-05-30",
    title: "Phase 1 — Auth + multi-tenancy",
    changes: [
      "Driver login (/login) + AuthGuard protecting app.blackvoltmobility.com.",
      "Tenant + Client models (multi-tenant ready); Black Volt seeded.",
      "Passenger Google sign-in backend (verify + find-or-create client).",
      "HMAC session cookie (owner/driver/passenger roles); sign-out.",
      "Fix: bake INTERNAL_API_URL at build so the /api proxy reaches the backend.",
    ],
  },
  {
    version: "0.3.2",
    date: "2026-05-30",
    title: "Mobile / responsive (native-app feel)",
    changes: [
      "Client + driver get fixed bottom tab bars on phones/tablets (<900px).",
      "Driver sidebar collapses into the tab bar + a 'More' bottom sheet.",
      "Ride & client tables become touch cards; KPIs a 2×2 grid.",
      "Floating AI chat lifts above the tab bar; safe-area aware.",
    ],
  },
  {
    version: "0.3.1",
    date: "2026-05-30",
    title: "Live domain + driver dashboard subdomain",
    changes: [
      "blackvoltmobility.com live via Cloudflare Tunnel → ROG.",
      "app.blackvoltmobility.com routes straight to the driver dashboard (host rewrite).",
      "Public site (apex/www) and dashboard (app) split by host.",
    ],
  },
  {
    version: "0.3.0",
    date: "2026-05-30",
    title: "Add ride (Manual + Smart) + SMS confirmation",
    changes: [
      "New /dashboard/add: create a reservation Manually or Smart.",
      "Smart mode: drop/paste/upload a screenshot → Claude vision extracts it (mock fallback); AI-filled fields tagged, missing ones flagged.",
      "Auto-generated confirmation SMS in the client's language: send now or copy.",
      "Passenger booking now shows a 'Confirmation sent by SMS' notice.",
    ],
  },
  {
    version: "0.2.0",
    date: "2026-05-30",
    title: "Driver Dashboard kit (from Claude Design)",
    changes: [
      "Dashboard shell: sidebar + topbar, collapses to an icon rail on mobile.",
      "Overview: KPIs, AI assistant card, today's rides, weekly bars.",
      "Rides: list + month/week Calendar; Clients CRM with search.",
      "Communications inbox: SMS / AI call / AI chat + AI-draft reply.",
      "Rates & brand editor with live fare preview. Bilingual EN/ES.",
    ],
  },
  {
    version: "0.1.0",
    date: "2026-05-30",
    title: "Passenger Web kit (from Claude Design)",
    changes: [
      "Booking flow: pickup/dropoff, route review, fare, Square pay, confirmation.",
      "My Trips: live tracking + flight status (mock data).",
      "Public driver profile /d/[slug] with QR onboarding card.",
      "Google sign-in modal + account (saved addresses, payment, prefs).",
      "Floating AI chat assistant; full design tokens + branded icon.",
    ],
  },
  {
    version: "0.0.1",
    date: "2026-05-29",
    title: "Phase 0 — Bootstrap",
    changes: [
      "New repo: FastAPI + Next.js 14 + Postgres + Redis + Docker stack.",
      "Black Volt brand theme (void black + electric cyan, Rajdhani + Inter).",
      "Bilingual shell: English default + Spanish switcher.",
      "Health endpoint + landing page + version history modal.",
    ],
  },
];
