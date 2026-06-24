# Client Onboarding Profile Gate — Design

**Date:** 2026-06-23
**Status:** Approved
**Phase:** 5 (Client portal — first slice)
**Branch:** `phase-5-onboarding-profile-gate`

## Problem

When a new client signs in with Google on `/book` to make their first booking,
Black Volt only captures `email`, `sub`, and `name` from Google. Google does
**not** provide a phone number or address. Today nothing forces a client to
provide a phone, so a passenger can create a booking with no way for the driver
to coordinate the ride (call, SMS, VAPI). There is also no passenger-facing way
to edit their own profile — only staff can, via the dashboard.

## Goal

Right after a successful Google sign-in on the booking flow, if the client's
profile is incomplete, show a blocking modal ("profile gate") that collects the
data Google can't give us before the booking can continue. Reuse the same
profile API so the account page becomes editable too.

## Scope decisions (locked)

- **Trigger:** Right after Google login, blocking the booking, **only when the
  profile is incomplete**. A returning client with a complete profile never sees it.
- **Fields:** First name (required, prefilled), Last name (required, prefilled),
  Phone (required), Default address (optional), SMS consent (checkbox).
- **Phone:** Collect only (no SMS OTP for now — OTP deferred to Phase 7). Validate
  + normalize to E.164, default to `+1`/US when 10 digits are given, accept valid
  international numbers, reject garbage. Stored normalized.
- **Names:** Separate `first_name` / `last_name` columns, prefilled from Google
  `given_name` / `family_name`; keep the existing `name` column synced to
  `"First Last"` so dashboard/rides are unaffected.
- **Architecture:** Approach A — modal gate inside the booking flow (reusable
  component), not a separate page or wizard step.
- **Out of scope (YAGNI):** Google `picture`/avatar storage; SMS OTP verification.

## Data model

`Client` (`backend/app/models/client.py`) gains three nullable columns via one
Alembic migration:

| Column | Type | Notes |
|---|---|---|
| `first_name` | `String(120)`, nullable | prefilled from Google `given_name` |
| `last_name` | `String(120)`, nullable | prefilled from Google `family_name` |
| `sms_consent` | `Boolean`, `default False`, not null | server default `false` |

The existing `name` column is retained as the display/full name and kept synced
to `f"{first_name} {last_name}".strip()` whenever names change.

**`profile_complete`** is a derived value, no stored flag:
```python
profile_complete = bool(client.first_name) and bool(client.last_name) and bool(client.phone)
```

## Google claims

`backend/app/services/auth.py::verify_google_id_token()` is extended to also
return `given_name` and `family_name` (already present in the ID token, currently
discarded). `login_google()` / `find_or_create_client()` persist them on first
creation and set `name` accordingly. Existing clients are untouched (the gate
backfills them).

## API

All passenger-facing; auth = passenger session, `client_id` taken from the token
(`cid`) — never from the request body.

### `GET /api/v1/me/profile`
Returns:
```json
{
  "first_name": "string|null",
  "last_name": "string|null",
  "name": "string|null",
  "email": "string|null",
  "phone": "string|null",
  "home_address": "string|null",
  "sms_consent": false,
  "profile_complete": true
}
```

### `PATCH /api/v1/me/profile`
Body (all optional, partial update):
```json
{
  "first_name": "string",
  "last_name": "string",
  "phone": "string",
  "home_address": "string",
  "sms_consent": true
}
```
- Validates + normalizes `phone` to E.164 (US default). Invalid → `422` with a
  field-level error message.
- Recomputes `name` from first/last when either changes.
- Returns the same shape as `GET`.

### Login + session
`POST /api/v1/auth/login/google` response and `GET /api/v1/auth/me` both gain
`profile_complete: bool` so the frontend can decide to open the gate without an
extra round trip.

### Phone validation helper
A single backend helper (e.g. `app/services/phone.py`) is the source of truth:
normalize to E.164, assume `+1` for bare 10-digit US numbers, accept valid
international E.164, reject anything else. The frontend does light pre-validation
for UX only; the backend is authoritative.

## Frontend

- **New component** `ProfileGate` (modal) under `frontend/components/bv/web/`:
  - First name (required, prefilled), Last name (required, prefilled),
    Phone (required, US placeholder + live validation), Default address
    (optional), SMS consent checkbox.
  - Save button disabled until required fields valid.
  - All strings via `t()` with keys added to **both** EN and ES dicts in
    `frontend/lib/i18n.tsx`.
  - **Mobile-first**: must render well at 390 / 820 / 1200 px.
- **Booking integration** (`frontend/components/bv/web/Booking.tsx`): after a
  successful Google login, if `profile_complete === false`, open `ProfileGate`
  before continuing; on save, close and resume the booking exactly where it was.
- **Account reuse** (`frontend/components/bv/web/Account.tsx`): currently
  read-only. Wire it to `PATCH /me/profile` so passengers can edit their own
  profile (targeted improvement aligned with the goal).
- New API helpers in `frontend/lib/` for `getProfile()` / `updateProfile()`.

## Error handling & edge cases

- Invalid phone → inline field error, modal stays open, booking not lost.
- Gate cannot be skipped while required fields are missing (save disabled).
  Dismissing the modal cancels the booking attempt — it never leaves a
  half-finished booking.
- Returning client with a complete profile → `profile_complete = true` → gate
  never shown.
- PATCH is idempotent; re-sending the same values is safe.
- Existing clients (created before this change) with no first/last name get the
  gate on their next booking, which backfills them.

## Testing

- **pytest** (`backend`):
  - Phone validation helper: US 10-digit → `+1…`, valid international, invalid
    rejected.
  - `PATCH /me/profile`: requires auth; scoped to session `client_id` (cannot
    edit another client); setting phone + names flips `profile_complete` to true;
    `name` recomputed.
  - `GET /me/profile` shape.
  - Login/`me` include `profile_complete`.
- **Frontend**: `tsc --noEmit` and `next lint` clean; Playwright visual check of
  the modal at 390 / 820 / 1200 px.

## Conventions

- Commits: conventional with scope (`feat(db):`, `feat(api):`, `feat(frontend):`),
  AI-assisted trailer.
- Alembic migration for the schema change; models re-exported from
  `__init__.py`. Customer-visible change → bump `frontend/lib/version.ts` +
  prepend `CHANGELOG.md`.
