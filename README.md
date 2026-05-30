# Black Volt Mobility

> **Silent Power. Premium Arrival.**
> Software platform for a premium electric chauffeur / airport-transfer service —
> a driver-owner dashboard, a passenger booking portal, and AI-driven
> communications. Built multi-tenant so it can be sold as SaaS to other drivers.

## What it does (MVP)

- **Booking**: passengers pick pickup/dropoff, see the route + price (Google
  Maps + a configurable rate engine), and pay with **Square**.
- **Driver dashboard**: rides calendar, client CRM, ride status, rate + brand
  editor — usable on web and mobile (native-app feel).
- **Client portal**: Google sign-in, saved profile/addresses, my-trips with live
  status, flight info.
- **Public profile + QR**: a trust page per driver (`/d/{slug}`) with a printable
  QR card; scanning adds the passenger to the driver's client list.
- **Communications**: AI chat in the portal, **SMS** (Twilio), **AI calls**
  (VAPI). Email (Resend) is wired but activated later.
- **Flight tracking**: live status + ETA for airport pickups.

## Stack

FastAPI + SQLAlchemy 2 (async) + Alembic + Postgres 16 + Redis 7 ·
Next.js 14 (App Router) + Tailwind · LLM = Kimi 2.6 + MiniMax M2.7 (fallback).
Bilingual: **English default + Spanish**.

## Run locally

```bash
cp .env.example .env   # fill in keys as you reach each phase
docker compose up -d --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3005 |
| Backend OpenAPI | http://localhost:8012/docs |
| Health | http://localhost:8012/api/v1/health |

### Backend tests

```bash
cd backend && pip install -r requirements.txt && pytest
```

See [`CLAUDE.md`](CLAUDE.md) for the port map, conventions, and phase plan.
