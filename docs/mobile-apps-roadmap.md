# Black Volt Mobility — Native apps roadmap (client app to App Store + Play Store)

**Decision (2026-07-17):** only the **client** app goes to the stores. The driver stays a
permanent installed PWA (already live with Web Push since v0.71). Technical approach: **Capacitor**
wrapping the live site (`server.url` → `https://blackvoltmobility.com`), not a React Native rebuild.

The work is phased. **Fase A shipped** (v0.82.0 — per-ride passenger↔driver chat, live on web + the
driver PWA). Fases B–D turn the site into a store-listed native app. **The critical path is the
developer/account paperwork below — it takes weeks and only the owner can do it, so start it now.**
Everything Claude builds in B/C can be done in parallel and doesn't need the accounts until the final
signing/submission step.

---

## ⏳ OWNER — start these today (the long pole)

| # | Action | Cost | Time | Notes |
|---|--------|------|------|-------|
| 1 | **D-U-N-S number** for the LLC | free | 5 days – 4 weeks | Check first if the LLC already has one at dnb.com. Apple's request form issues one faster (~5–8 business days) than D&B direct (up to 30). **Blocks #2 and #3.** |
| 2 | **Apple Developer Program** — Organization enrollment | $99 / yr | 2–7 days after #1 | Needs the D-U-N-S + exact legal LLC name + a public website + a verifiable phone. |
| 3 | **Google Play Console** — organization account | $25 once | 1–2 weeks | Also asks for D-U-N-S + identity verification. Org accounts are exempt from the 12-tester / 14-day rule that personal accounts have. |
| 4 | **Firebase project** (for push) | free | ~1 hr, after #2 | New project → add an Android app (package + SHA-1 → `google-services.json`) and an iOS app (bundle id). Upload the **APNs Auth Key (.p8)** from Apple Developer → Keys. Generate a service-account JSON → give it to Claude to put in the VPS `.env` (never committed). |

Nothing in Fases B/C below is blocked by these until the moment we sign real builds — Claude can build
and test on a simulator (free) and an Android debug keystore in the meantime.

---

## Fase B — Capacitor shell (Claude, no store dependency)

A thin native wrapper that loads the live site. Delivers a real installable app on a simulator with
zero backend changes.

- New `mobile/` project: `capacitor.config.ts` (`appId: com.blackvoltmobility.app`, `appName: "Black
  Volt"`, `server.url` → production, `allowNavigation` for the site + `*.squareup.com` for Square 3DS,
  `appendUserAgent: "BlackVoltApp"`), splash/status bar in brand `#0A0A0F`, offline fallback page.
- `frontend/lib/native.ts`: `isNativeApp()` detection → hide the "Install app" button / A2HS hint and
  skip Web Push registration when running inside the native app (push comes via FCM in Fase C).
- Local tooling needed on the build Mac: **Xcode 16+** (+ CocoaPods) and **Android Studio** (SDK 35).
- **Known gap Fase B leaves for C:** Google Sign-In won't work inside the webview (Google blocks OAuth
  in webviews) — that's exactly what Fase C's native sign-in fixes.

## Fase C — Native auth + native push (Claude, backend deployable first, v0.83.0)

1. **Native Google Sign-In** (`@capgo/capacitor-social-login` — maintained, Android Credential
   Manager, and it also does Apple Sign-In). Backend accepts multiple OAuth audiences (web + iOS +
   Android client IDs) via a new `GOOGLE_CLIENT_IDS` setting that falls back to today's single ID.
2. **Sign in with Apple** — required by Apple (guideline 4.8) once Google login is offered. New
   `POST /auth/login/apple`, `clients.apple_sub` column. iOS-only button.
3. **App session** — `Authorization: Bearer` fallback in the backend session read (+ fix `/auth/me`,
   which reads the cookie directly today); longer token TTL for the app + silent re-auth; token stored
   in Capacitor Preferences; a fetch interceptor adds the header when native. WKWebView can purge
   cookies with a remote `server.url`, so Bearer is the reliable path.
4. **Native push = FCM for both platforms** — new `push_subscriptions.platform` column + `services/fcm.py`;
   branch by platform inside `_send_one` so every existing call-site (including Fase A's chat push and
   the pickup reminders) is untouched. Web Push for the driver PWA stays exactly as-is. Migration 0047.
   No-ops safely until the Firebase service-account credentials are in the VPS `.env`.

## Fase D — Store listings + review (owner + Claude)

- **Assets:** iPhone 6.9" screenshots (≥3), Play feature graphic 1024×500 + icon 512, listings in EN
  and ES. iPhone-only (no iPad).
- **Privacy:** audit `/privacy` to cover in-app messaging + push tokens + "no device GPS" (addresses
  are typed text). App Privacy / Data Safety: Contact info, User Content (messages), Identifiers,
  Purchases (Square) — linked, **no tracking, no Location**. **Apple 5.1.1(v) requires account
  deletion** — add a "Delete account" action to `/account` if missing (bloqueante barato).
- **Review notes:** a Google demo account (no 2FA) with a sample ride; state explicitly *"Payments are
  for physical transportation services rendered outside the app, processed by Square, per guideline
  3.1.5(a)"*; minimum-functionality (4.2) is covered by native push + native login + in-app chat +
  end-to-end booking.
- **Rollout:** Play internal testing (minutes) → TestFlight internal (beta review hours–1 day) → owner
  tests on their Galaxy + iPhone → Play production (≤7 days first review) + App Store review (24–48h
  typical; budget 1–2 weeks for a possible rejection cycle).

---

## Status

- **Fase A** — ✅ shipped v0.82.0 (`46ab29b`), live + verified in prod.
- **Fase C backend (Android part)** — ✅ shipped 2026-07-18. Multi-audience Google Sign-In, `Bearer`
  sessions + `/auth/me` fix + native token/TTL, and FCM push plumbing (migration 0047, `services/fcm.py`,
  `platform` column). Retrocompatible and a no-op until the Android OAuth client ID + Firebase creds
  exist. 766 backend tests pass. **This is the "backend deployable first" step of the Android track.**
- **Remaining for Android:** (a) Capacitor shell + native Google Sign-In/push wiring — needs
  **Android Studio + JDK on the build machine** (not installed in the current env); (b) Firebase
  project (#4) for real push; (c) Google Play Console (#3) for submission.
- **Owner: begin the account paperwork (#1–#4 above) now** — it's the multi-week critical path.
  For Android specifically the order is cheaper/faster: **Google Play ($25) + Firebase (free)** don't
  need the Apple D-U-N-S, so Android can reach the store well before iOS.

Full technical plan: `~/.claude/plans/atomic-plotting-hare.md`. Memory: `project_blackvolt_ride_messaging.md`.
