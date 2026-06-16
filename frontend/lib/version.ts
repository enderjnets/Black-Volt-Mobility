export interface VersionEntry {
  version: string;
  date: string;
  title: string;
  changes: string[];
}

export const CURRENT_VERSION = "0.26.1";

export const CHANGELOG: VersionEntry[] = [
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
