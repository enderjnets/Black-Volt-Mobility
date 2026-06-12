# CLAUDE.md — Black Volt Mobility

> Project anchor for Claude (and any AI agent) working in this repo. Read
> top-to-bottom before changing things. Anti-patterns are non-negotiable.

## What this is

**Black Volt Mobility** is the software platform for a premium electric
chauffeur / airport-transfer service (Kia EV9, Denver/Aurora CO; owner-driver
Ender). It provides a **driver-owner dashboard**, a **passenger portal**, a
**public profile + QR onboarding**, **AI-driven communications** (chat, SMS,
VAPI calls), **flight tracking**, and **Square payments**.

It is built **multi-tenant** (every domain table has `tenant_id`) so it can be
sold as **SaaS to other drivers**, even though the MVP serves a single tenant
(Black Volt). Architecture mirrors **Eko AI Realtors** (`~/Eko-AI-RealEstate`)
but generalizes it from single-tenant to multi-tenant. The repo/GitHub name is
`Black-Volt-Mobility`; the brand name is **Black Volt Mobility**.

## CRITICAL Anti-patterns

1. **NEVER use Anthropic OAuth (Claude Max token) for product LLM traffic.** Use
   **Kimi + MiniMax** only (anthropic-messages protocol via the `anthropic` SDK
   with custom `base_url`). OAuth is for personal Claude Code/OpenClaw use.
2. **NEVER bake API keys, phone numbers, or tokens into committed files.** Read
   from `.env` (gitignored).
3. **NEVER reuse Realtors' resources** — its Twilio number (+17205946249), its
   Resend subdomain, its ports/containers, or its Cloudflare tunnels. Black Volt
   gets its own everything.
4. **NEVER touch the Eko stacks** on the ROG (`eko-*`, `eko-*-main`,
   `eko-realestate-*`, `eko-frontend-pricing-v2`). Use only `blackvolt-*`.
5. **NEVER ship a `*_SIMULATED=true` channel with `APP_ENV=production`.** The
   backend logs a WARN when prod + auth-off; investigate before green-lighting.
6. **Every domain model carries `tenant_id`; every query scopes by tenant.** Do
   not write tenant-blind queries — it breaks the SaaS path.

## Port map (ROG `100.88.47.99` / `10.0.0.240`)

Coexists with the four Eko stacks. Use exactly these:

| Service | Port | Container |
|---|---|---|
| Postgres | **5435** | `blackvolt-db` |
| Redis | **6382** | `blackvolt-redis` |
| Backend (FastAPI) | **8012** | `blackvolt-backend` |
| Frontend (Next.js) | **3005** | `blackvolt-frontend` |

## Stack

- **Backend**: FastAPI + SQLAlchemy 2 (async) + Alembic + Postgres 16 + Redis 7
  + `anthropic` SDK.
- **Frontend**: Next.js 14 (App Router) + Tailwind + lucide-react. **i18n** is a
  client context (`lib/i18n.tsx`, `useI18n().t(key)`) — **English default +
  Spanish** switcher. All UI strings go through `t()`; add new strings to BOTH
  dictionaries. AI replies detect + answer in the client's language.
- **LLM**: Kimi 2.6 `kimi-for-coding` primary, MiniMax M2.7 fallback, inline per
  request. All calls go through `app/services/llm.py`.
- **Brand**: Void Black `#0A0A0F`, Electric Cyan `#00E5FF`, Obsidian Gray, Cloud
  Silver, Arctic White. Fonts Rajdhani (display) + Inter (body). Tagline
  "Silent Power. Premium Arrival." Source assets on the ROG at
  `/home/enderj/.openclaw/workspace/black_volt/` + `/blackvolt/`.

## Conventions

- **Commits**: conventional with scope (`feat(api):`, `feat(db):`,
  `feat(frontend):`, `fix(...)`, `chore:`, `docs:`). End AI-assisted commits with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Branches & releases**: `main` is the stable trunk. Each phase in its own
  branch (`phase-1-auth`, `phase-2-booking`, …). At phase close: PR → merge →
  tag `v0.X.0` → `gh release create`. Any customer-visible change bumps
  `frontend/lib/version.ts` + prepends `CHANGELOG.md`.
- **Database**: Alembic for all schema changes; models in `backend/app/models/`,
  re-exported from `__init__.py` so autogenerate sees them. Wrap str-enums with
  `pg_enum()` from `app/db/base.py`. Async sessions via `get_db()`.
- **Code style**: backend `ruff` (line 100); frontend `next lint` + `tsc
  --noEmit` zero errors. Default to NO comments — only explain the non-obvious
  *why*. Tests: `pytest` + `pytest-asyncio`, fixtures inline per file.

## Phase status

- ✅ **Phase 0** — Bootstrap (`v0.0.1`): repo + Docker stack + brand shell +
  bilingual landing + health endpoint.
- ✅ Phase 1 — Auth + multi-tenancy + profiles (`v0.4.x`)
- ✅ Phase 2 — Booking core: rides + RateConfig + pricing engine + Google Maps
  adapter (simulated default) + quote/rides/rate-config API (`v0.5.0`)
- ✅ Phase 3 — Square payments + driver subscriptions (`v0.23.0`): booking
  card payments + Operator subscription landing/checkout + signature-verified
  webhooks. Code merged + released; live activation is the owner checklist in
  `docs/subscriptions-activation.md` (Square plan ids, `driver.` DNS, webhook key,
  prod flip).
- ⏳ Phase 4 — Driver dashboard
- ⏳ Phase 5 — Client portal
- ⏳ Phase 6 — Public profile + QR onboarding
- ⏳ Phase 7 — Communications (AI chat + SMS + VAPI)
- ⏳ Phase 8 — Flight tracking
- ⏳ Phase 9 — Production deploy (VPS + ROG demo)

## References

- **Plan**: `~/.claude/plans/quiero-que-empecemos-un-effervescent-star.md`
- **Memory**: `~/.claude/projects/-Users-enderj/memory/project_black_volt_mobility.md`
- **Architecture mirror**: `~/Eko-AI-RealEstate` (+ its `CLAUDE.md`)
